# Recurrence math for subscriptions: next due date, monthly equivalent.
# All functions are pure (date in -> date out) so they are trivially testable.
from __future__ import annotations

import calendar
import datetime as dt

CYCLES = ("monthly", "yearly", "custom")

# Days per month on average (Gregorian): used to normalise custom cycles.
DAYS_PER_MONTH = 365.25 / 12.0


def _clamp(year: int, month: int, day: int) -> dt.date:
    """Same calendar day clamped to the month's real length (Jan 31 -> Feb 28)."""
    last = calendar.monthrange(year, month)[1]
    return dt.date(year, month, min(day, last))


def add_months(d: dt.date, n: int, anchor_day: int | None = None) -> dt.date:
    """d + n months; the day clamps to month length but stays anchored to
    `anchor_day` (default d.day): Jan 31 -> Feb 28 -> Mar 31, not -> Mar 28."""
    anchor = d.day if anchor_day is None else anchor_day
    month_index = d.month - 1 + n
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    return _clamp(year, month, anchor)


def add_years(d: dt.date, n: int, anchor_day: int | None = None) -> dt.date:
    """d + n years; Feb 29 clamps to Feb 28 on non-leap years and the anchor
    restores Feb 29 on the next leap year."""
    anchor = d.day if anchor_day is None else anchor_day
    return _clamp(d.year + n, d.month, anchor)


def next_due_date(due: dt.date, cycle: str, custom_days: int | None = None,
                  anchor_day: int | None = None) -> dt.date:
    """The date of the NEXT charge after `due`."""
    if cycle == "monthly":
        return add_months(due, 1, anchor_day)
    if cycle == "yearly":
        return add_years(due, 1, anchor_day)
    if cycle == "custom":
        if not custom_days or custom_days <= 0:
            raise ValueError("custom cycle needs a positive custom_days")
        return due + dt.timedelta(days=custom_days)
    raise ValueError(f"unknown cycle {cycle!r}")


def nth_occurrence(start: dt.date, cycle: str, n: int,
                   custom_days: int | None = None,
                   anchor_day: int | None = None) -> dt.date:
    """The n-th charge date counting `start` itself as occurrence 0."""
    if n < 0:
        raise ValueError("n must be >= 0")
    d = start
    for _ in range(n):
        d = next_due_date(d, cycle, custom_days, anchor_day)
    return d


def monthly_equivalent(amount: float, cycle: str, custom_days: int | None = None) -> float:
    """Normalise any billing cycle to a per-month figure."""
    if cycle == "monthly":
        return amount
    if cycle == "yearly":
        return amount / 12.0
    if cycle == "custom":
        if not custom_days or custom_days <= 0:
            raise ValueError("custom cycle needs a positive custom_days")
        return amount * (365.25 / custom_days) / 12.0
    raise ValueError(f"unknown cycle {cycle!r}")


def trial_ending_soon(trial_end: dt.date | None, today: dt.date | None = None,
                      warn_days: int = 3) -> bool:
    """True when a trial ends within `warn_days` days (today inclusive)."""
    if trial_end is None:
        return False
    today = today or dt.date.today()
    return dt.timedelta(0) <= (trial_end - today) <= dt.timedelta(days=warn_days)


def upcoming_dates(start: dt.date, cycle: str, custom_days: int | None,
                   horizon_days: int, today: dt.date | None = None,
                   anchor_day: int | None = None) -> list[dt.date]:
    """All charge dates within `horizon_days` from today, starting from `start`.

    `start` is the stored next_due_date; occurrences strictly in the past are
    rolled forward so a stale DB still produces future charges.
    """
    today = today or dt.date.today()
    d = start
    # Roll forward past missed charges (bounded: at most ~200 years of months).
    for _ in range(2400):
        if d >= today:
            break
        d = next_due_date(d, cycle, custom_days, anchor_day)
    else:
        return []
    out = []
    while (d - today).days <= horizon_days:
        out.append(d)
        d = next_due_date(d, cycle, custom_days, anchor_day)
    return out
