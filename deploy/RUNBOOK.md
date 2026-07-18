# Frugl demo — deploy runbook

Serves the FastAPI backend + static frontend from ONE origin at `127.0.0.1:47896`, exposed
publicly via a Tailscale Funnel **path** (`/frugl`). No access key — the demo is openly
shareable and **auto-disables** at a server-enforced UTC expiry.

This reflects the live deployment. Everything here is outward-facing (sudo + a public URL).
Do it deliberately, in order.

Reality check — the live instance right now:
- Code: dedicated checkout `/home/claude/frugl-deploy` at `origin/main` (NOT the shared
  `cp-advisor` dev tree, which a second session edits).
- Public URL: `https://<node>.ts.net/frugl/` (share WITH the trailing slash).
- Gate: expiry-only, set in `/etc/frugl.env`.

---

## 0. Preflight — prove `claude -p` works AS the service will run it

Extraction shells out to `claude -p`. Under systemd it runs as `User=claude` with
`HOME=/home/claude`; if OAuth creds aren't found there, every extraction silently 401s and
serves the degraded fallback. Verify the exact environment BEFORE installing anything:

```bash
env -i HOME=/home/claude PATH=/usr/local/bin:/usr/bin:/bin \
  /usr/bin/claude --strict-mcp-config --mcp-config '{"mcpServers":{}}' \
  --output-format json -p <<<'odgovori zgolj z besedo: ok'
```

Expect a JSON envelope with `"result"` containing `ok`. A 401 / login prompt / empty
result means the creds aren't visible in that env — fix that first (re-auth as `claude`),
or extraction will be dead on stage while the UI looks fine.

## 1. Deploy checkout (isolated from the dev tree)

```bash
git clone https://github.com/Zanoxlr/frugl.git /home/claude/frugl-deploy   # or: git -C /home/claude/frugl-deploy pull
cd /home/claude/frugl-deploy && python3 -m pytest -q                        # expect all green
```

Serving from its own checkout keeps the public demo off whatever half-built work is sitting
uncommitted in `cp-advisor`.

## 2. Write the env file (expiry + leads path) — NOT in the repo

```bash
EXPIRES=$(date -u -d '+28 hours' +%FT%TZ)          # UTC. VPS tz is Slovenia (UTC+2).
sudo tee /etc/frugl.env >/dev/null <<EOF
FRUGL_DEMO_GATE=1
FRUGL_DEMO_EXPIRES=$EXPIRES
FRUGL_LEADS_PATH=/home/claude/frugl-deploy/data/leads.jsonl
EOF
sudo chmod 600 /etc/frugl.env
echo "expires: $EXPIRES"
```

The expiry is enforced server-side (`auth.py`): while `FRUGL_DEMO_GATE=1` and now < expiry,
every `/api/*` is open; at/after the expiry (or a missing/unparseable value) every `/api/*`
returns 403 and the app goes blank. To extend, edit this file and `systemctl restart frugl-api`.

## 3. Install + start the unit

The committed unit `deploy/frugl-api.service` already sets `WorkingDirectory=/home/claude/frugl-deploy`,
`User=claude`, `HOME=/home/claude`, and `EnvironmentFile=/etc/frugl.env`.

```bash
sudo cp /home/claude/frugl-deploy/deploy/frugl-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now frugl-api
sudo systemctl status frugl-api --no-pager
```

## 4. Verify locally (still private)

```bash
curl -s 127.0.0.1:47896/api/health                                          # {"ok":true,"gate":true}
curl -s -o /dev/null -w '%{http_code}\n' 127.0.0.1:47896/api/state          # 200 (open until expiry)
curl -s -o /dev/null -w '%{http_code}\n' 127.0.0.1:47896/                   # 200 (frontend)
```

If health shows `"gate":false`, the EnvironmentFile didn't load — check `/etc/frugl.env`
perms and `systemctl show frugl-api -p EnvironmentFiles`. After the expiry passes,
`/api/state` returns 403 (that's the demo self-disabling; not a bug).

## 5. Expose publicly via a Tailscale Funnel PATH  ← the public step

Funnel's public ports (443 / 8443 / 10000) are already used by other services on this node,
so Frugl mounts as a **path** on 443 instead of a dedicated port. Tailscale strips the
`/frugl` prefix before proxying, and the frontend derives its API base from the URL, so the
app works under the subpath with no code change.

```bash
sudo tailscale funnel --bg --set-path /frugl http://127.0.0.1:47896
tailscale funnel status                 # confirm the /frugl mount + the *.ts.net name
```

Share `https://<node>.ts.net/frugl/` **with the trailing slash** (without it, the derived
base still resolves the API, but the relative `<head>` manifest link points at the site root
— the slash keeps everything consistent).

## 6. Rotate / kill

```bash
# extend the window:
sudo sed -i "s|^FRUGL_DEMO_EXPIRES=.*|FRUGL_DEMO_EXPIRES=$(date -u -d '+1 day' +%FT%TZ)|" /etc/frugl.env && sudo systemctl restart frugl-api
# hard-disable NOW (expire immediately -> every /api 403s, app goes blank):
sudo sed -i "s|^FRUGL_DEMO_EXPIRES=.*|FRUGL_DEMO_EXPIRES=2000-01-01T00:00:00Z|" /etc/frugl.env && sudo systemctl restart frugl-api
# pull just the public path (service keeps running privately):
sudo tailscale funnel --set-path /frugl off
# stop the service entirely:
sudo systemctl disable --now frugl-api
```

## Leads

Captured to `FRUGL_LEADS_PATH` (`data/leads.jsonl`, gitignored) as one JSON object per line:
`{id, createdAt(UTC), vertical, degraded, profile, offer}`. `degraded:true` marks a capture
where extraction or the engine fell back — watch for a run of these (a dead `claude -p`).

## Notes carried from the build

- Endpoints that extract are **sync def** on purpose (FastAPI threadpool), so a ~30s blocking
  extraction never freezes the live SSE chat stream.
- `WorkingDirectory` matters: `dev_serve.py` mounts the frontend and the leads path defaults
  resolve relative to it (the unit pins it to the deploy checkout).
- No access key: the gate is time-only. If you ever need per-user access, that's a new
  mechanism, not this one.
- cloudflared is NOT installed on this box; Tailscale Funnel is the supported tunnel.
