"""
Contract lifecycle: turn a subscription's `contract` facts into a derived status the
frontend renders directly. Pure + deterministic: `as_of` (today) is injectable, so tests
pin a date and the demo can pin one via `?asOf=` / the FRUGL_DEMO_TODAY env var.

Never raises on malformed contract data. Anything it can't parse degrades to `no_contract`
(a line with no lock), so a bad date can never 500 a dashboard render.

The renewal window ("~1 month before it's over, look up a better offer") opens far enough
ahead of the cancellation-notice deadline that the user still has runway to act:
    window = max(RENEWAL_WINDOW_DAYS, noticePeriodDays + NOTICE_RUNWAY_DAYS)
so a 30-day-notice contract starts offering at 44 days out, leaving ~14 days to cancel.
"""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta

RENEWAL_WINDOW_DAYS = 30      # the user-facing "about a month before it ends"
NOTICE_RUNWAY_DAYS = 14       # always open the window at least this long before the notice deadline

# status values (kept as module constants so callers / tests don't hardcode strings)
NO_CONTRACT = "no_contract"   # no lock: variable energy, water, statutory — switch anytime
ACTIVE = "active"             # locked, more than a window away — nothing to do
RENEWAL_WINDOW = "renewal_window"  # inside the window — attach the better offer here
EXPIRED = "expired"           # past the end date


def _parse_date(value):
    """Accept 'YYYY-MM-DD' (or a date/datetime); return a `date` or None. Never raises."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return None


def resolve_today(as_of=None):
    """Resolution order: explicit `as_of` -> FRUGL_DEMO_TODAY env -> real today.
    An unparseable override silently falls back to the real date (never crash a render)."""
    for candidate in (as_of, os.environ.get("FRUGL_DEMO_TODAY")):
        parsed = _parse_date(candidate)
        if parsed is not None:
            return parsed
    return date.today()


def _days_in_month(year, month):
    first_next = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return (first_next - date(year, month, 1)).days


def _add_months(start, months):
    """Calendar-correct month add, clamping the day to the target month's length."""
    index = start.month - 1 + months
    year = start.year + index // 12
    month = index % 12 + 1
    day = min(start.day, _days_in_month(year, month))
    return date(year, month, day)


def _end_date(contract):
    """endDate wins if present; otherwise derive startDate + termMonths. None if neither."""
    end = _parse_date(contract.get("endDate"))
    if end is not None:
        return end
    start = _parse_date(contract.get("startDate"))
    term = contract.get("termMonths")
    if start is None or not isinstance(term, int) or term <= 0:
        return None
    return _add_months(start, term)


def _no_contract(end=None, auto=False):
    return {
        "status": NO_CONTRACT,
        "endDate": end.isoformat() if end else None,
        "daysRemaining": None,
        "noticeDeadline": None,
        "daysToNoticeDeadline": None,
        "actionRequired": False,
        "autoRenews": bool(auto),
    }


def lifecycle(contract, as_of=None):
    """Derived lifecycle for one subscription line.

    `contract` is the line's `contract` block (or None). Returns a dict the frontend
    renders directly. `contract=None`, `termMonths` null/0, or an underivable end date
    all mean `no_contract` (switch anytime, no countdown).
    """
    today = resolve_today(as_of)

    if not isinstance(contract, dict):
        return _no_contract()

    auto = bool(contract.get("autoRenews", False))
    term = contract.get("termMonths")
    end = _end_date(contract)

    # no lock, or we can't tell when it ends -> treat as freely switchable
    if term in (None, 0) or end is None:
        return _no_contract(end, auto)

    days_remaining = (end - today).days

    notice_days = contract.get("noticePeriodDays")
    notice_deadline = None
    days_to_notice = None
    if isinstance(notice_days, int) and notice_days >= 0:
        notice_deadline = end - timedelta(days=notice_days)
        days_to_notice = (notice_deadline - today).days
        window = max(RENEWAL_WINDOW_DAYS, notice_days + NOTICE_RUNWAY_DAYS)
    else:
        window = RENEWAL_WINDOW_DAYS

    if days_remaining < 0:
        status = EXPIRED
        action = auto  # already rolled over, but if it auto-renewed it's still worth acting on
    elif days_remaining <= window:
        status = RENEWAL_WINDOW
        action = True
    else:
        status = ACTIVE
        action = False

    return {
        "status": status,
        "endDate": end.isoformat(),
        "daysRemaining": days_remaining,
        "noticeDeadline": notice_deadline.isoformat() if notice_deadline else None,
        "daysToNoticeDeadline": days_to_notice,
        "actionRequired": action,
        "autoRenews": auto,
    }


def annotate_subscriptions(subscriptions, as_of=None):
    """Attach a `lifecycle` block to each line (non-mutating shallow copies).
    Convenience for the eventual /api/state wiring; kept here so the endpoint layer
    stays a one-liner and the logic is fully unit-tested in isolation."""
    out = []
    for sub in subscriptions or []:
        line = dict(sub)
        line["lifecycle"] = lifecycle(sub.get("contract"), as_of=as_of)
        out.append(line)
    return out


def due_for_renewal(subscriptions, as_of=None):
    """Lines whose lifecycle status is `renewal_window` (or `expired` + autoRenews),
    each paired with its lifecycle block. The raw material for /api/renewals; the offer
    (compare() result) is attached by the endpoint layer, not here."""
    due = []
    for sub in subscriptions or []:
        lc = lifecycle(sub.get("contract"), as_of=as_of)
        if lc["status"] == RENEWAL_WINDOW or (lc["status"] == EXPIRED and lc["autoRenews"]):
            due.append({"line": sub, "lifecycle": lc})
    return due
