"""Demo auto-expiry for the public Frugl deployment.

Not auth — the only job is to make the public demo URL stop working after ~1 day. When
ARMED, every `/api/*` request is allowed until a server-enforced UTC expiry, then 403.
No key: the demo is meant to be openly shareable while it's live.

Enablement is explicit via `FRUGL_DEMO_GATE`. The deploy's EnvironmentFile sets it plus
the expiry; local dev and the test suite leave it unset, so the gate is simply off there.

  FRUGL_DEMO_GATE     truthy -> arm the expiry (deploy sets this)
  FRUGL_DEMO_EXPIRES  ISO-8601 UTC instant; at/after it, every /api request is 403
"""
import os
from datetime import datetime, timezone

GATE_ENV = "FRUGL_DEMO_GATE"
EXPIRES_ENV = "FRUGL_DEMO_EXPIRES"

_TRUTHY = {"1", "true", "on", "yes"}


def is_armed():
    return os.environ.get(GATE_ENV, "").strip().lower() in _TRUTHY


def _parse_expires(raw):
    """Parse an ISO-8601 instant to tz-aware UTC. A naive value is ASSUMED UTC (the
    documented contract) so a naive-vs-aware comparison can never raise. Raises
    ValueError on anything unparseable -> caller treats it as fail-closed."""
    dt = datetime.fromisoformat(raw.strip())
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def demo_gate_error(provided_key=None):
    """Return a reason string when the request must be blocked, else None. Disarmed ->
    open. Armed -> open until the expiry; a missing/unparseable/passed expiry -> 403
    (fail closed, so a misconfigured deploy self-disables rather than staying up forever).
    `provided_key` is accepted and ignored for call-site compatibility."""
    if not is_armed():
        return None

    raw_exp = os.environ.get(EXPIRES_ENV)
    if not raw_exp:
        return "demo expiry not configured"
    try:
        expires = _parse_expires(raw_exp)
    except (ValueError, TypeError):
        return "demo expiry unparseable"

    if datetime.now(timezone.utc) >= expires:
        return "demo expired"

    return None
