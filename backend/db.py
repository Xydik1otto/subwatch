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
    CHECK (cycle != 'custom' OR (custom_days IS NOT NULL AND custom_days > 0))
);
"""


def connect(db_path: str | None = None) -> sqlite3.Connection:
    path = db_path or DB_PATH
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


def init_db(db_path: str | None = None) -> sqlite3.Connection:
    conn = connect(db_path)
    conn.commit()
    return conn
