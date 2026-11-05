# SQLite schema + connection helpers (stdlib sqlite3, no ORM dependency).
import os
import sqlite3

DB_PATH = os.environ.get("SUBWATCH_DB",
                         os.path.join(os.path.dirname(__file__), "..", "subwatch.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS subscriptions (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT NOT NULL,
    amount         REAL NOT NULL CHECK (amount >= 0),
    currency       TEXT NOT NULL DEFAULT 'USD',
    cycle          TEXT NOT NULL CHECK (cycle IN ('monthly','yearly','custom')),
    custom_days    INTEGER,
    anchor_day     INTEGER,
    next_due_date  TEXT NOT NULL,
    trial_end_date TEXT,
    notes          TEXT,
    tags           TEXT,
    active         INTEGER NOT NULL DEFAULT 1,
    times_used_per_month REAL,
    paused         INTEGER NOT NULL DEFAULT 0,
    CHECK (cycle != 'custom' OR (custom_days IS NOT NULL AND custom_days > 0))
);

CREATE TABLE IF NOT EXISTS price_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    subscription_id INTEGER NOT NULL
                    REFERENCES subscriptions(id) ON DELETE CASCADE,
    amount          REAL NOT NULL,
    changed_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS alerts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    subscription_id INTEGER NOT NULL
                    REFERENCES subscriptions(id) ON DELETE CASCADE,
    old_amount      REAL NOT NULL,
    new_amount      REAL NOT NULL,
    currency        TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    seen            INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_price_history_sub
    ON price_history(subscription_id);

CREATE INDEX IF NOT EXISTS idx_alerts_seen
    ON alerts(seen, created_at);
"""

# Columns added after the MVP schema; existing DBs are migrated on connect.
_EXTRA_SUBSCRIPTION_COLUMNS: dict[str, str] = {
    "times_used_per_month": "REAL",
    "paused": "INTEGER NOT NULL DEFAULT 0",
    "cancel_planned": "INTEGER NOT NULL DEFAULT 0",
    "cancel_deadline": "TEXT",
    # family mode: кому належить, хто платить, частка платника (%)
    "owner": "TEXT",
    "payer": "TEXT",
    "share_pct": "REAL NOT NULL DEFAULT 100",
}


def _migrate(conn: sqlite3.Connection) -> None:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(subscriptions)")}
    for name, ddl in _EXTRA_SUBSCRIPTION_COLUMNS.items():
        if name not in cols:
            conn.execute(f"ALTER TABLE subscriptions ADD COLUMN {name} {ddl}")


def connect(db_path: str | None = None) -> sqlite3.Connection:
    path = db_path or DB_PATH
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    _migrate(conn)
    return conn


def init_db(db_path: str | None = None) -> sqlite3.Connection:
    conn = connect(db_path)
    conn.commit()
    return conn
