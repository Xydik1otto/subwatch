# First-run demo: optional sample data so a brand-new user sees how the
# tracker works before entering their own subscriptions.
from __future__ import annotations

import datetime as dt

# (name, amount, currency, cycle, tags, owner, payer, share_pct, next_due offset)
DEMO_SUBSCRIPTIONS = [
    ("Netflix", 15.49, "USD", "monthly", "video", "сім'я", "Тарас", 100, 5),
    ("Spotify Family", 16.99, "USD", "monthly", "music", "сім'я", "Тарас", 50, 12),
    ("iCloud+ 200GB", 2.99, "USD", "monthly", "cloud", "Оля", "Оля", 100, 3),
    ("Adobe Creative Cloud", 59.99, "USD", "monthly", "software", "робота", None, 100, 18),
    ("Kyivstar", 150.0, "UAH", "monthly", "mobile", None, "Оля", 100, 9),
    ("NordVPN", 99.48, "USD", "yearly", "vpn", "сім'я", "Тарас", 100, 120),
    ("Скасувати: Prime Video", 5.99, "USD", "monthly", "video", None, None, 100, 2),
]


def seed_demo(conn, today: dt.date | None = None) -> list[int]:
    """Insert demo subscriptions (idempotent: only if the DB is empty).
    Returns the list of created ids ([] if data already exists)."""
    today = today or dt.date.today()
    n = conn.execute("SELECT COUNT(*) AS n FROM subscriptions").fetchone()["n"]
    if n:
        return []
    ids = []
    with conn:
        for name, amount, ccy, cycle, tags, owner, payer, share, offset in DEMO_SUBSCRIPTIONS:
            due = today + dt.timedelta(days=offset)
            trial = (today + dt.timedelta(days=7)) if "Prime" in name else None
            cur = conn.execute(
                "INSERT INTO subscriptions(name, amount, currency, cycle,"
                " anchor_day, next_due_date, trial_end_date, tags, notes,"
                " owner, payer, share_pct)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (name, amount, ccy, cycle, due.day, due.isoformat(),
                 trial.isoformat() if trial else None, tags,
                 "Демо-дані — можна видалити", owner, payer, share))
            from . import history
            history.record_amount(conn, cur.lastrowid, amount)
            ids.append(cur.lastrowid)
    return ids
