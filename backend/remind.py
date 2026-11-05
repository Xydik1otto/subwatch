# CLI reminders: `python -m backend.remind [--days 7] [--notify]`
# Prints upcoming charges / expiring trials. --notify opens a local
# Windows message box (no cloud, no daemons, no dependencies).
from __future__ import annotations

import argparse
import datetime as dt
import sys

from .db import connect


def collect(days: int, db_path: str | None = None):
    from . import schedule
    conn = connect(db_path)
    rows = conn.execute(
        "SELECT * FROM subscriptions WHERE active = 1 AND paused = 0 "
        "ORDER BY next_due_date"
    ).fetchall()
    today = dt.date.today()
    charges, trials = [], []
    for r in rows:
        start = dt.date.fromisoformat(r["next_due_date"])
        for d in schedule.upcoming_dates(start, r["cycle"], r["custom_days"], days, today):
            charges.append((d, r))
        if r["trial_end_date"]:
            te = dt.date.fromisoformat(r["trial_end_date"])
            if dt.timedelta(0) <= te - today <= dt.timedelta(days=3):
                trials.append((te, r))
    charges.sort(key=lambda x: x[0])
    trials.sort(key=lambda x: x[0])
    return charges, trials


def render(charges, trials) -> str:
    lines = []
    if charges:
        lines.append("Upcoming charges:")
        for d, r in charges:
            lines.append(f"  {d.isoformat()}  {r['name']:<28} "
                         f"{r['amount']:>8.2f} {r['currency']}  ({r['cycle']})")
    if trials:
        lines.append("Trials ending within 3 days — cancel or you will be charged:")
        for d, r in trials:
            lines.append(f"  {d.isoformat()}  {r['name']:<28} "
                         f"{r['amount']:>8.2f} {r['currency']}")
    if not lines:
        lines.append(f"Nothing due in the horizon. Export the .ics instead.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="subwatch-remind",
                                 description="Show upcoming subscription charges")
    ap.add_argument("--days", type=int, default=7, help="horizon in days (default 7)")
    ap.add_argument("--notify", action="store_true",
                    help="also show a local notification (Windows message box)")
    ap.add_argument("--db", default=None, help="path to subwatch.db")
    args = ap.parse_args(argv)

    charges, trials = collect(args.days, args.db)
    text = render(charges, trials)
    print(text)

    if args.notify and sys.platform == "win32":
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, text, "subwatch", 0x40)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
