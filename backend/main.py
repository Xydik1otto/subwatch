# FastAPI application: local-first subscription tracker.
from __future__ import annotations

import datetime as dt
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import ics, schedule
from .db import DB_PATH, connect

app = FastAPI(title="subwatch", version="0.1.0",
              description="Local-first subscription tracker — no cloud, no accounts")

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

TRIAL_WARN_DAYS = 3


def get_conn():
    return connect(os.environ.get("SUBWATCH_DB", DB_PATH))


class SubscriptionIn(BaseModel):
    name: str
    amount: float = Field(ge=0)
    currency: str = "USD"
    cycle: str = Field(pattern="^(monthly|yearly|custom)$")
    custom_days: int | None = Field(default=None, gt=0)
    anchor_day: int | None = Field(default=None, ge=1, le=31)
    next_due_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    trial_end_date: str | None = Field(default=None,
                                       pattern=r"^\d{4}-\d{2}-\d{2}$")
    notes: str | None = None
    tags: str | None = None


def _row_dict(r) -> dict:
    d = dict(r)
    d["monthly_equivalent"] = round(schedule.monthly_equivalent(
        d["amount"], d["cycle"], d["custom_days"]), 4)
    return d


def _effective_anchor(body: SubscriptionIn) -> int | None:
    """Monthly/yearly cycles get an anchor day = next_due day unless given."""
    if body.cycle == "custom":
        return None
    if body.anchor_day:
        return body.anchor_day
    return int(body.next_due_date[8:10])


# --- API ---------------------------------------------------------------------

@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/subscriptions")
def create_subscription(body: SubscriptionIn):
    if body.cycle == "custom" and not body.custom_days:
        raise HTTPException(422, "custom cycle needs custom_days")
    anchor = _effective_anchor(body)
    conn = get_conn()
    with conn:
        cur = conn.execute(
            "INSERT INTO subscriptions(name, amount, currency, cycle, custom_days,"
            " anchor_day, next_due_date, trial_end_date, notes, tags)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (body.name, body.amount, body.currency.upper(), body.cycle,
             body.custom_days, anchor, body.next_due_date, body.trial_end_date,
             body.notes, body.tags),
        )
    row = conn.execute("SELECT * FROM subscriptions WHERE id = ?",
                       (cur.lastrowid,)).fetchone()
    return _row_dict(row)


@app.get("/api/subscriptions")
def list_subscriptions(sort: str = "next_due_date"):
    conn = get_conn()
    order = {
        "next_due_date": "next_due_date ASC",
        "amount": "amount DESC",
        "monthly": "amount * CASE cycle WHEN 'monthly' THEN 1 WHEN 'yearly' THEN 1.0/12 ELSE 30.4375/custom_days END DESC",
        "name": "name COLLATE NOCASE ASC",
    }.get(sort, "next_due_date ASC")
    rows = conn.execute(
        f"SELECT * FROM subscriptions WHERE active = 1 ORDER BY {order}").fetchall()
    return [_row_dict(r) for r in rows]


@app.patch("/api/subscriptions/{sub_id}")
def update_subscription(sub_id: int, body: SubscriptionIn):
    if body.cycle == "custom" and not body.custom_days:
        raise HTTPException(422, "custom cycle needs custom_days")
    anchor = _effective_anchor(body)
    conn = get_conn()
    if not conn.execute("SELECT 1 FROM subscriptions WHERE id = ?", (sub_id,)).fetchone():
        raise HTTPException(404, "subscription not found")
    with conn:
        conn.execute(
            "UPDATE subscriptions SET name=?, amount=?, currency=?, cycle=?,"
            " custom_days=?, anchor_day=?, next_due_date=?, trial_end_date=?,"
            " notes=?, tags=? WHERE id=?",
            (body.name, body.amount, body.currency.upper(), body.cycle,
             body.custom_days, anchor, body.next_due_date, body.trial_end_date,
             body.notes, body.tags, sub_id),
        )
    row = conn.execute("SELECT * FROM subscriptions WHERE id = ?", (sub_id,)).fetchone()
    return _row_dict(row)


@app.delete("/api/subscriptions/{sub_id}")
def delete_subscription(sub_id: int):
    conn = get_conn()
    with conn:
        cur = conn.execute("DELETE FROM subscriptions WHERE id = ?", (sub_id,))
    if cur.rowcount == 0:
        raise HTTPException(404, "subscription not found")
    return {"deleted": sub_id}


@app.post("/api/subscriptions/{sub_id}/mark-paid")
def mark_paid(sub_id: int):
    """Charge happened: roll next_due_date one cycle forward."""
    conn = get_conn()
    row = conn.execute("SELECT * FROM subscriptions WHERE id = ?", (sub_id,)).fetchone()
    if not row:
        raise HTTPException(404, "subscription not found")
    due = dt.date.fromisoformat(row["next_due_date"])
    anchor = row["anchor_day"] if "anchor_day" in row.keys() else None
    nxt = schedule.next_due_date(due, row["cycle"], row["custom_days"], anchor)
    with conn:
        conn.execute("UPDATE subscriptions SET next_due_date = ? WHERE id = ?",
                     (nxt.isoformat(), sub_id))
    return {"id": sub_id, "next_due_date": nxt.isoformat()}


@app.get("/api/summary")
def summary():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM subscriptions WHERE active = 1").fetchall()
    by_ccy: dict[str, float] = {}
    for r in rows:
        by_ccy[r["currency"]] = by_ccy.get(r["currency"], 0.0) + \
            schedule.monthly_equivalent(r["amount"], r["cycle"], r["custom_days"])
    today = dt.date.today()
    next_due = conn.execute(
        "SELECT * FROM subscriptions WHERE active = 1 "
        "ORDER BY next_due_date ASC LIMIT 1").fetchone()
    return {
        "active_count": len(rows),
        "monthly_by_currency": {k: round(v, 2) for k, v in sorted(by_ccy.items())},
        "yearly_by_currency": {k: round(v * 12, 2) for k, v in sorted(by_ccy.items())},
        "next_due": _row_dict(next_due) if next_due else None,
    }


@app.get("/api/upcoming")
def upcoming(days: int = 30):
    """Charges (and trial ends) within `days` from today."""
    conn = get_conn()
    rows = conn.execute("SELECT * FROM subscriptions WHERE active = 1").fetchall()
    today = dt.date.today()
    out = []
    for r in rows:
        start = dt.date.fromisoformat(r["next_due_date"])
        anchor = r["anchor_day"] if "anchor_day" in r.keys() else None
        for d in schedule.upcoming_dates(start, r["cycle"], r["custom_days"], days,
                                         today, anchor):
            out.append({"subscription": _row_dict(r), "date": d.isoformat(),
                        "kind": "charge"})
        if r["trial_end_date"]:
            te = dt.date.fromisoformat(r["trial_end_date"])
            if dt.timedelta(0) <= te - today <= dt.timedelta(days=days):
                out.append({"subscription": _row_dict(r), "date": te.isoformat(),
                            "kind": "trial_end",
                            "warning": (te - today).days <= TRIAL_WARN_DAYS})
    out.sort(key=lambda x: x["date"])
    return out


@app.get("/api/trials")
def trials(warn_days: int = TRIAL_WARN_DAYS):
    """Trials ending within warn_days — the 'cancel before they charge you' list."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM subscriptions WHERE active = 1 AND trial_end_date IS NOT NULL"
    ).fetchall()
    today = dt.date.today()
    out = []
    for r in rows:
        te = dt.date.fromisoformat(r["trial_end_date"])
        left = (te - today).days
        if 0 <= left <= warn_days:
            out.append({**_row_dict(r), "days_left": left})
    out.sort(key=lambda x: x["days_left"])
    return out


@app.get("/api/export.ics")
def export_ics(days: int = 90):
    conn = get_conn()
    rows = conn.execute("SELECT * FROM subscriptions WHERE active = 1").fetchall()
    data = ics.build_ics(ics.subscription_events(rows, days))
    return Response(content=data, media_type="text/calendar",
                    headers={"Content-Disposition":
                             'attachment; filename="subwatch.ics"'})


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
