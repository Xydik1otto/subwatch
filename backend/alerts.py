# Price-change alerts (outbox): whenever a subscription's amount changes,
# an alert row is written. The UI shows a badge until alerts are marked seen.
from __future__ import annotations

import datetime as dt


def record_alert(conn, sub_id: int, old_amount: float, new_amount: float,
                 currency: str, when: dt.date | None = None) -> int:
    """Insert one alert into the outbox. Returns the alert id."""
    cur = conn.execute(
        "INSERT INTO alerts(subscription_id, old_amount, new_amount, currency,"
        " created_at, seen) VALUES (?,?,?,?,?,0)",
        (sub_id, old_amount, new_amount, currency,
         (when or dt.date.today()).isoformat()))
    return cur.lastrowid


def _alert_dict(r, name: str | None = None) -> dict:
    d = {
        "id": r["id"],
        "subscription_id": r["subscription_id"],
        "old_amount": r["old_amount"],
        "new_amount": r["new_amount"],
        "currency": r["currency"],
        "created_at": r["created_at"],
        "seen": bool(r["seen"]),
    }
    if name is not None:
        d["name"] = name
    pct = ((r["new_amount"] - r["old_amount"]) / r["old_amount"] * 100
           if r["old_amount"] else 0.0)
    d["pct"] = round(pct, 1)
    d["direction"] = "up" if r["new_amount"] > r["old_amount"] else "down"
    if name is not None:
        sign = "+" if d["pct"] >= 0 else ""
        d["text"] = (f"{name}: {r['old_amount']:.2f}→{r['new_amount']:.2f}"
                     f" ({sign}{d['pct']}% {r['currency']})")
    return d


def list_alerts(conn, unseen_only: bool = True) -> list[dict]:
    q = ("SELECT a.*, s.name AS name FROM alerts a"
         " JOIN subscriptions s ON s.id = a.subscription_id")
    if unseen_only:
        q += " WHERE a.seen = 0"
    q += " ORDER BY a.created_at DESC, a.id DESC"
    return [_alert_dict(r, r["name"]) for r in conn.execute(q).fetchall()]


def unseen_count(conn) -> int:
    return conn.execute("SELECT COUNT(*) AS n FROM alerts WHERE seen = 0"
                        ).fetchone()["n"]


def mark_seen(conn, alert_id: int) -> bool:
    cur = conn.execute("UPDATE alerts SET seen = 1 WHERE id = ?", (alert_id,))
    return cur.rowcount > 0


def mark_all_seen(conn) -> int:
    cur = conn.execute("UPDATE alerts SET seen = 1 WHERE seen = 0")
    return cur.rowcount
