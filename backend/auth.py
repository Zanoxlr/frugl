"""Demo access gate for the public Frugl deployment.

Not real auth — a single shared key + a server-enforced UTC expiry so the demo URL can
be handed out and then self-disables. The one rule that matters: when the gate is ARMED
it fails CLOSED. Any missing/blank key, missing/unparseable/expired expiry, or a wrong
header -> 403. It never authorizes on a misconfiguration (the `None == None` fail-open
trap).

Enablement is explicit via `FRUGL_DEMO_GATE`. The deploy's EnvironmentFile sets it (plus
the key + expiry); local dev and the test suite leave it unset, so the gate is simply
off there. That keeps the public path strict without forcing a key into every dev run.

  FRUGL_DEMO_GATE     truthy -> arm the gate (deploy sets this)
  FRUGL_DEMO_KEY      the shared secret; frontend echoes it as `x-frugl-key`
  FRUGL_DEMO_EXPIRES  ISO-8601 UTC instant; at/after it, every request is 403
"""
import hmac
import os
from datetime import datetime, timezone

GATE_ENV = "FRUGL_DEMO_GATE"
KEY_ENV = "FRUGL_DEMO_KEY"
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


def demo_gate_error(provided_key):
    """Return a reason string when the request must be blocked, else None.

    When the gate is disarmed -> None (open). When armed, every failure mode returns a
    reason (403), so the default is always CLOSED."""
    if not is_armed():
        return None

    key = os.environ.get(KEY_ENV)
    if not key:
        return "demo key not configured"

    if not provided_key or not hmac.compare_digest(str(provided_key), key):
        return "invalid or missing demo key"

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
