# Frugl demo — deploy runbook

Serves the FastAPI backend + static frontend from ONE origin at `127.0.0.1:47896`, gated
behind a demo key with a server-enforced UTC expiry, exposed publicly via Tailscale Funnel.
The demo self-disables when the expiry passes.

Everything here is outward-facing (sudo + a public URL). Do it deliberately, in order.

---

## 0. Preflight — prove `claude -p` works AS the service will run it

Extraction shells out to `claude -p`. Under systemd it runs as `User=claude` with
`HOME=/home/claude`; if OAuth creds aren't found there, every extraction silently 401s and
serves the degraded fallback. Verify the exact environment BEFORE installing anything:

```bash
sudo -u claude env -i HOME=/home/claude PATH=/usr/local/bin:/usr/bin:/bin \
  /usr/bin/claude --strict-mcp-config --mcp-config '{"mcpServers":{}}' \
  --output-format json -p <<<'odgovori zgolj z besedo: ok'
```

Expect a JSON envelope with `"result"` containing `ok`. A 401 / login prompt / empty
result means the creds aren't visible in that env — fix that first (re-auth as `claude`),
or extraction will be dead on stage while the UI looks fine.

## 1. Write the env file (key + UTC expiry + leads path) — NOT in the repo

```bash
KEY=$(head -c 18 /dev/urandom | base64 | tr -dc 'a-zA-Z0-9' | head -c 24)
sudo tee /etc/frugl.env >/dev/null <<EOF
FRUGL_DEMO_GATE=1
FRUGL_DEMO_KEY=$KEY
# UTC instant. VPS tz is Slovenia (UTC+2): 12:00 UTC = 14:00 local. ~1 day out.
FRUGL_DEMO_EXPIRES=2026-07-19T18:00:00Z
FRUGL_LEADS_PATH=/home/claude/cp-advisor/data/leads.jsonl
EOF
sudo chmod 600 /etc/frugl.env
echo "demo key: $KEY"
```

The expiry is enforced server-side (`auth.py`): at/after it, every `/api/*` returns 403 and
the app goes blank. To extend, edit this file and `systemctl restart frugl-api`.

## 2. Install + start the unit

```bash
sudo cp /home/claude/cp-advisor/deploy/frugl-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now frugl-api
sudo systemctl status frugl-api --no-pager
```

## 3. Verify locally (still private)

```bash
curl -s 127.0.0.1:47896/api/health                              # {"ok":true,"gate":true}
curl -s 127.0.0.1:47896/config.js                               # window.FRUGL_KEY="<key>";
curl -s -o /dev/null -w '%{http_code}\n' 127.0.0.1:47896/api/state                       # 403 (no key)
curl -s -o /dev/null -w '%{http_code}\n' -H "x-frugl-key: <key>" 127.0.0.1:47896/api/state  # 200
```

If health shows `"gate":false`, the EnvironmentFile didn't load — check `/etc/frugl.env`
perms and `systemctl show frugl-api -p EnvironmentFiles`.

## 4. Expose publicly via Tailscale Funnel  ← this is the public step

Funnel must be allowed in the tailnet ACL (`nodeAttrs` -> `funnel`), and TCP 443/8443/10000
open. Then:

```bash
sudo tailscale funnel --bg 47896        # serves https on the node's *.ts.net name
tailscale funnel status                 # prints the public URL
```

Share the `https://<node>.ts.net/` URL **with the key appended out-of-band** (the frontend
pulls the key from `/config.js`, so the URL alone is enough to load the app; the key in the
URL is not needed — just send the URL).

## 5. Rotate / kill

```bash
# rotate the key (invalidates every shared link):
sudo sed -i "s/^FRUGL_DEMO_KEY=.*/FRUGL_DEMO_KEY=$NEWKEY/" /etc/frugl.env && sudo systemctl restart frugl-api
# hard-disable NOW (expire immediately):
sudo sed -i "s/^FRUGL_DEMO_EXPIRES=.*/FRUGL_DEMO_EXPIRES=2000-01-01T00:00:00Z/" /etc/frugl.env && sudo systemctl restart frugl-api
# pull the public URL:
sudo tailscale funnel reset
# stop the service entirely:
sudo systemctl disable --now frugl-api
```

## Leads

Captured to `FRUGL_LEADS_PATH` (`data/leads.jsonl`, gitignored) as one JSON object per line:
`{id, createdAt(UTC), vertical, degraded, profile, offer}`. `degraded:true` marks a capture
where extraction or the engine fell back — watch for a run of these (a dead `claude -p`).

## Notes carried from the build

- Endpoints that extract are **sync def** on purpose (FastAPI threadpool), so a 30s blocking
  extraction never freezes the live SSE chat stream.
- `WorkingDirectory` matters: `StaticFiles(directory="frontend")` and the leads path default
  are resolved relative to it.
- cloudflared is NOT installed on this box; Tailscale Funnel is the supported tunnel.
