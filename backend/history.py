# Price history: every amount change of a subscription is recorded so the
# user can see "Netflix: 15.49→16.99 (+9.6% за 8 міс)" at a glance.
from __future__ import annotations

import datetime as dt

DAYS_PER_MONTH = 365.25 / 12.0


def record_amount(conn, sub_id: int, amount: float,
                  when: dt.date | None = None) -> None:
    conn.execute(
        "INSERT INTO price_history(subscription_id, amount, changed_at)"
        " VALUES (?,?,?)",
        (sub_id, amount, (when or dt.date.today()).isoformat()))


def _months_between(old: dt.date, new: dt.date) -> int:
    return max(1, round((new - old).days / DAYS_PER_MONTH))


def format_change(name: str, old: float, new: float, months: int) -> str:
    pct = (new - old) / old * 100 if old else 0.0
    sign = "+" if pct >= 0 else ""
    return f"{name}: {old:.2f}→{new:.2f} ({sign}{pct:.1f}% за {months} міс)"


def price_change_summaries(conn) -> list[dict]:
    """One summary per subscription that has >1 recorded amount."""
    out = []
    subs = conn.execute("SELECT id, name FROM subscriptions ORDER BY name").fetchall()
    for sub in subs:
        rows = conn.execute(
            "SELECT amount, changed_at FROM price_history"
            " WHERE subscription_id = ? ORDER BY changed_at, id",
            (sub["id"],)).fetchall()
        if len(rows) < 2:
            continue
        changes = []
        prev_amount = None
        prev_date = None
        for r in rows:
            entry = {"amount": r["amount"], "date": r["changed_at"]}
            if prev_amount is not None:
                months = _months_between(
                    dt.date.fromisoformat(prev_date),
                    dt.date.fromisoformat(r["changed_at"]))
                entry["from"] = prev_amount
                entry["pct"] = round((r["amount"] - prev_amount) /
                                     prev_amount * 100, 1) if prev_amount else 0.0
                entry["months"] = months
                entry["text"] = format_change(sub["name"], prev_amount,
                                              r["amount"], months)
            changes.append(entry)
            prev_amount, prev_date = r["amount"], r["changed_at"]
        out.append({"subscription_id": sub["id"], "name": sub["name"],
                    "changes": changes})
    return out
