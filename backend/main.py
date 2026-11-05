# FastAPI application: local-first subscription tracker.
from __future__ import annotations

import csv
import datetime as dt
import io
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import alerts as alerts_mod, cancel_kb, csvimport, demo as demo_mod, family, history, ics, native_accel, projection as projection_mod, rates, schedule, tags as tags_mod
from .db import DB_PATH, connect

app = FastAPI(title="subwatch", version="1.0.0",
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
    times_used_per_month: float | None = Field(default=None, ge=0)
    # family mode
    owner: str | None = None
    payer: str | None = None
    share_pct: float = Field(default=100, ge=0, le=100)


def _row_dict(r) -> dict:
    d = dict(r)
    d["monthly_equivalent"] = round(schedule.monthly_equivalent(
        d["amount"], d["cycle"], d["custom_days"]), 4)
    uses = d.get("times_used_per_month")
    d["cost_per_use"] = (round(d["monthly_equivalent"] / uses, 4)
                         if uses and uses > 0 else None)
    d["paused"] = bool(d.get("paused"))
    d["cancel_planned"] = bool(d.get("cancel_planned"))
    d["owner"] = d.get("owner")
    d["payer"] = d.get("payer")
    d["share_pct"] = d.get("share_pct", 100)
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
            " anchor_day, next_due_date, trial_end_date, notes, tags,"
            " times_used_per_month, owner, payer, share_pct)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (body.name, body.amount, body.currency.upper(), body.cycle,
             body.custom_days, anchor, body.next_due_date, body.trial_end_date,
             body.notes, body.tags, body.times_used_per_month,
             body.owner, body.payer, body.share_pct),
        )
        history.record_amount(conn, cur.lastrowid, body.amount)
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
    # Paused subscriptions stay visible but sort to the bottom of the list.
    rows = conn.execute(
        f"SELECT * FROM subscriptions WHERE active = 1 "
        f"ORDER BY paused ASC, {order}").fetchall()
    return [_row_dict(r) for r in rows]


@app.post("/api/subscriptions/{sub_id}/pause")
def pause_subscription(sub_id: int):
    """Freeze a subscription: visible in the list, excluded from totals,
    upcoming calendar, ICS export and reminders until unpaused."""
    return _set_paused(sub_id, 1)


@app.post("/api/subscriptions/{sub_id}/unpause")
def unpause_subscription(sub_id: int):
    return _set_paused(sub_id, 0)


def _set_paused(sub_id: int, paused: int):
    conn = get_conn()
    if not conn.execute("SELECT 1 FROM subscriptions WHERE id = ?",
                        (sub_id,)).fetchone():
        raise HTTPException(404, "subscription not found")
    with conn:
        conn.execute("UPDATE subscriptions SET paused = ? WHERE id = ?",
                     (paused, sub_id))
    row = conn.execute("SELECT * FROM subscriptions WHERE id = ?",
                       (sub_id,)).fetchone()
    return {"id": sub_id, "paused": bool(row["paused"])}


@app.patch("/api/subscriptions/{sub_id}")
def update_subscription(sub_id: int, body: SubscriptionIn):
    if body.cycle == "custom" and not body.custom_days:
        raise HTTPException(422, "custom cycle needs custom_days")
    anchor = _effective_anchor(body)
    conn = get_conn()
    old_row = conn.execute("SELECT * FROM subscriptions WHERE id = ?",
                           (sub_id,)).fetchone()
    if not old_row:
        raise HTTPException(404, "subscription not found")
    with conn:
        conn.execute(
            "UPDATE subscriptions SET name=?, amount=?, currency=?, cycle=?,"
            " custom_days=?, anchor_day=?, next_due_date=?, trial_end_date=?,"
            " notes=?, tags=?, times_used_per_month=?, owner=?, payer=?,"
            " share_pct=? WHERE id=?",
            (body.name, body.amount, body.currency.upper(), body.cycle,
             body.custom_days, anchor, body.next_due_date, body.trial_end_date,
             body.notes, body.tags, body.times_used_per_month,
             body.owner, body.payer, body.share_pct, sub_id),
        )
        if old_row["amount"] != body.amount:
            history.record_amount(conn, sub_id, body.amount)
            # price-change alert (outbox): the user must notice the increase
            alerts_mod.record_alert(conn, sub_id, old_row["amount"],
                                    body.amount, body.currency.upper())
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


class PlanCancelIn(BaseModel):
    cancel_deadline: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")


@app.post("/api/subscriptions/{sub_id}/plan-cancel")
def plan_cancel(sub_id: int, body: PlanCancelIn):
    """Mark a subscription 'plan to cancel' with a hard deadline (the date
    before the next charge). The deadline lands in the ICS export and gets
    a red badge in the UI."""
    conn = get_conn()
    if not conn.execute("SELECT 1 FROM subscriptions WHERE id = ?",
                        (sub_id,)).fetchone():
        raise HTTPException(404, "subscription not found")
    try:
        dt.date.fromisoformat(body.cancel_deadline)   # real calendar date
    except ValueError:
        raise HTTPException(422, "cancel_deadline is not a real date")
    with conn:
        conn.execute(
            "UPDATE subscriptions SET cancel_planned = 1, cancel_deadline = ?"
            " WHERE id = ?", (body.cancel_deadline, sub_id))
    row = conn.execute("SELECT * FROM subscriptions WHERE id = ?",
                       (sub_id,)).fetchone()
    return {"id": sub_id, "cancel_planned": True,
            "cancel_deadline": row["cancel_deadline"]}


@app.post("/api/subscriptions/{sub_id}/unplan-cancel")
def unplan_cancel(sub_id: int):
    """Clear the 'plan to cancel' status (e.g. you changed your mind)."""
    conn = get_conn()
    if not conn.execute("SELECT 1 FROM subscriptions WHERE id = ?",
                        (sub_id,)).fetchone():
        raise HTTPException(404, "subscription not found")
    with conn:
        conn.execute(
            "UPDATE subscriptions SET cancel_planned = 0, cancel_deadline = NULL"
            " WHERE id = ?", (sub_id,))
    return {"id": sub_id, "cancel_planned": False, "cancel_deadline": None}


@app.get("/api/to-cancel")
def to_cancel():
    """Everything marked 'plan to cancel', sorted by deadline."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM subscriptions WHERE active = 1 AND cancel_planned = 1"
        " ORDER BY cancel_deadline ASC").fetchall()
    return [_row_dict(r) for r in rows]


@app.get("/api/summary")
def summary(base: str | None = None):
    """Totals per currency; with ?base=USD/EUR/... everything is converted
    through ECB reference rates (cached, stale-tolerant)."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM subscriptions WHERE active = 1 AND paused = 0").fetchall()
    by_ccy: dict[str, float] = {}
    for r in rows:
        by_ccy[r["currency"]] = by_ccy.get(r["currency"], 0.0) + \
            schedule.monthly_equivalent(r["amount"], r["cycle"], r["custom_days"])
    today = dt.date.today()
    next_due = conn.execute(
        "SELECT * FROM subscriptions WHERE active = 1 AND paused = 0 "
        "ORDER BY next_due_date ASC LIMIT 1").fetchone()
    paused_count = conn.execute(
        "SELECT COUNT(*) AS n FROM subscriptions WHERE active = 1 AND paused = 1"
    ).fetchone()["n"]
    out = {
        "active_count": len(rows),
        "paused_count": paused_count,
        "monthly_by_currency": {k: round(v, 2) for k, v in sorted(by_ccy.items())},
        "yearly_by_currency": {k: round(v * 12, 2) for k, v in sorted(by_ccy.items())},
        "next_due": _row_dict(next_due) if next_due else None,
    }
    if base:
        base = base.upper()
        fx = rates.get_rates()
        if not fx or (base not in fx and base != "EUR"):
            raise HTTPException(
                503, "currency conversion unavailable: no ECB rates "
                     "(offline and no cached rates)")
        converted = {
            ccy: rates.convert(v, ccy, base, fx)
            for ccy, v in by_ccy.items()}
        missing = [c for c, v in converted.items() if v is None]
        if missing:
            raise HTTPException(503, f"no ECB rate for: {', '.join(sorted(missing))}")
        monthly = sum(converted.values())
        out["base"] = base
        out["monthly_in_base"] = round(monthly, 2)
        out["yearly_in_base"] = round(monthly * 12, 2)
    return out


@app.get("/api/today")
def charges_today():
    """Charges due today (and trials ending today) — the source for
    web notifications about money leaving the account right now."""
    conn = get_conn()
    today = dt.date.today().isoformat()
    rows = conn.execute(
        "SELECT * FROM subscriptions WHERE active = 1 AND paused = 0 "
        "AND (next_due_date = ? OR trial_end_date = ?)",
        (today, today)).fetchall()
    return [_row_dict(r) for r in rows]


@app.get("/api/upcoming")
def upcoming(days: int = 30):
    """Charges (and trial ends) within `days` from today."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM subscriptions WHERE active = 1 AND paused = 0").fetchall()
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
    rows = conn.execute(
        "SELECT * FROM subscriptions WHERE active = 1 AND paused = 0").fetchall()
    data = ics.build_ics(ics.subscription_events(rows, days))
    return Response(content=data, media_type="text/calendar",
                    headers={"Content-Disposition":
                             'attachment; filename="subwatch.ics"'})


# --- dashboard: worst offenders -------------------------------------------------

@app.get("/api/worst-offenders")
def worst_offenders(limit: int = 5):
    """Top-N subscriptions by monthly equivalent — the 'worst offenders' list.

    share_of_currency_monthly_pct is computed within the subscription's own
    currency, since totals of different currencies are never mixed.
    """
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM subscriptions WHERE active = 1 AND paused = 0").fetchall()
    items = [_row_dict(r) for r in rows]
    totals: dict[str, float] = {}
    for it in items:
        totals[it["currency"]] = (totals.get(it["currency"], 0.0) +
                                  it["monthly_equivalent"])
    for it in items:
        total = totals[it["currency"]]
        it["share_of_currency_monthly_pct"] = (
            round(it["monthly_equivalent"] / total * 100, 1) if total else 0.0)
    items.sort(key=lambda d: (-d["monthly_equivalent"], d["name"].lower()))
    return items[:max(0, limit)]


# --- annual projection ----------------------------------------------------------

@app.get("/api/projection")
def projection(months: int = 12, today: str | None = None):
    """Per-calendar-month sums of actual charges for the next `months` months.

    `today` (YYYY-MM-DD) is an optional override for previews/tests; the SVG
    chart always uses the real current date.
    """
    if months < 1 or months > 36:
        raise HTTPException(422, "months must be between 1 and 36")
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM subscriptions WHERE active = 1 AND paused = 0").fetchall()
    as_of = dt.date.fromisoformat(today) if today else dt.date.today()
    proj = projection_mod.monthly_projection(rows, as_of, months)
    return {"months": proj, "primary_currency": projection_mod.primary_currency(proj)}


@app.get("/api/projection.svg")
def projection_svg(months: int = 12):
    if months < 1 or months > 36:
        raise HTTPException(422, "months must be between 1 and 36")
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM subscriptions WHERE active = 1 AND paused = 0").fetchall()
    proj = projection_mod.monthly_projection(rows, dt.date.today(), months)
    ccy = projection_mod.primary_currency(proj) or "USD"
    svg = projection_mod.build_svg(proj, ccy)
    return Response(content=svg, media_type="image/svg+xml")


# --- tag analytics ---------------------------------------------------------------

@app.get("/api/tags")
def tag_analytics():
    """Monthly spend grouped by tag (comma-separated `tags` column).

    Untagged subscriptions are aggregated under the '(без тегу)' key.
    Currencies are reported separately — never mixed.
    """
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM subscriptions WHERE active = 1").fetchall()
    breakdown = tags_mod.monthly_by_tag(rows)
    untagged = next((t for t in breakdown if t["tag"] == ""), None)
    if untagged:
        untagged["tag"] = "(без тегу)"
    return {
        "tags": breakdown,
        "primary_currency": tags_mod.primary_currency(breakdown),
    }


@app.get("/api/tags.svg")
def tag_analytics_svg():
    """SVG pie chart: share of monthly spend per tag (primary currency)."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM subscriptions WHERE active = 1").fetchall()
    breakdown = tags_mod.monthly_by_tag(rows)
    ccy = tags_mod.primary_currency(breakdown) or "USD"
    return Response(content=tags_mod.build_svg(breakdown, ccy),
                    media_type="image/svg+xml")


# --- CSV import ---------------------------------------------------------------

class ImportAnalyzeIn(BaseModel):
    csv: str
    preset: str | None = None   # 'revolut' | 'wise' — див. GET /api/import/presets


class ImportCandidateIn(BaseModel):
    name: str
    amount: float = Field(ge=0)
    currency: str = "USD"
    cycle: str = Field(pattern="^(monthly|yearly|custom)$")
    custom_days: int | None = Field(default=None, gt=0)
    next_due_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    description: str | None = None


class ImportConfirmIn(BaseModel):
    candidates: list[ImportCandidateIn]


@app.get("/api/import/presets")
def import_presets():
    """Known bank statement presets (column mappings by default)."""
    return [{"id": pid, "label": p["label"], "columns": p["columns"]}
            for pid, p in csvimport.PRESETS.items()]


@app.post("/api/import/analyze")
def import_analyze(body: ImportAnalyzeIn):
    """Parse a bank CSV and return recurring-payment candidates.

    With `preset` ('revolut'/'wise') the header row is matched against the
    bank's known column names instead of guessing.
    """
    try:
        txns, candidates = native_accel.parse_and_detect(body.csv, body.preset)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return {"parsed_rows": len(txns), "candidates": candidates}


@app.post("/api/import/confirm")
def import_confirm(body: ImportConfirmIn):
    """Create subscriptions from confirmed import candidates."""
    created = []
    conn = get_conn()
    with conn:
        for c in body.candidates:
            cur = conn.execute(
                "INSERT INTO subscriptions(name, amount, currency, cycle,"
                " custom_days, next_due_date, notes) VALUES (?,?,?,?,?,?,?)",
                (c.name, c.amount, c.currency.upper(), c.cycle, c.custom_days,
                 c.next_due_date,
                 f"Imported from CSV: {c.description or c.name}"),
            )
            history.record_amount(conn, cur.lastrowid, c.amount)
            created.append(cur.lastrowid)
    rows = [conn.execute("SELECT * FROM subscriptions WHERE id = ?",
                         (sid,)).fetchone() for sid in created]
    return {"created": [_row_dict(r) for r in rows]}


# --- family mode ---------------------------------------------------------------

@app.get("/api/family")
def family_breakdown():
    """Who pays for what: per-payer share-adjusted totals (never mixing
    currencies) plus the owner/payer/share of every active subscription."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM subscriptions WHERE active = 1").fetchall()
    return family.family_breakdown(rows)


# --- cancel assistant: static knowledge base -----------------------------------

@app.get("/api/cancel-assistant")
def cancel_assistant_catalogue():
    """Catalogue of the top-20 services with official cancellation links."""
    return cancel_kb.all_services()


@app.get("/api/cancel-assistant/{service_id}")
def cancel_assistant_guide(service_id: str):
    """Step-by-step cancellation guide (UA + EN) for one service."""
    g = cancel_kb.guide(service_id)
    if not g:
        raise HTTPException(404, "service not found in cancel-assistant knowledge base")
    return g


@app.get("/api/subscriptions/{sub_id}/cancel-guide")
def subscription_cancel_guide(sub_id: int):
    """Match a subscription's name against the knowledge base and return
    the matching cancellation guide, or 404 if the service is unknown."""
    conn = get_conn()
    row = conn.execute("SELECT name FROM subscriptions WHERE id = ?",
                       (sub_id,)).fetchone()
    if not row:
        raise HTTPException(404, "subscription not found")
    sid = cancel_kb.match_service(row["name"])
    if not sid:
        raise HTTPException(404, "no cancel-assistant guide for this service name")
    return {"subscription_id": sub_id, "matched_name": row["name"],
            "service_id": sid, **cancel_kb.guide(sid)}


# --- first-run demo -------------------------------------------------------------

class DemoSeedOut(BaseModel):
    created: list[int]
    already_had_data: bool


@app.post("/api/demo/seed")
def demo_seed():
    """Load demo subscriptions on an empty database (opt-in from the UI
    banner). If data already exists, nothing is created."""
    conn = get_conn()
    ids = demo_mod.seed_demo(conn)
    return DemoSeedOut(created=ids, already_had_data=ids == [])


# --- data safety: one-click export of everything --------------------------------

@app.get("/api/export.json")
def export_json():
    """Full export: subscriptions, price history, price-change alerts."""
    conn = get_conn()
    subs = [dict(r) for r in conn.execute(
        "SELECT * FROM subscriptions ORDER BY id").fetchall()]
    hist = [dict(r) for r in conn.execute(
        "SELECT * FROM price_history ORDER BY id").fetchall()]
    alerts_rows = [dict(r) for r in conn.execute(
        "SELECT * FROM alerts ORDER BY id").fetchall()]
    return {
        "exported_at": dt.datetime.now().isoformat(timespec="seconds"),
        "subscriptions": subs,
        "price_history": hist,
        "alerts": alerts_rows,
    }


@app.get("/api/export.csv")
def export_csv():
    """Subscriptions as a flat CSV (one row per subscription)."""
    conn = get_conn()
    rows = conn.execute("SELECT * FROM subscriptions ORDER BY id").fetchall()
    cols = list(rows[0].keys()) if rows else ["id", "name", "amount", "currency"]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
    writer.writeheader()
    for r in rows:
        writer.writerow({c: r[c] for c in cols})
    data = buf.getvalue()
    return Response(content=data, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition":
                             'attachment; filename="subwatch-export.csv"'})


# --- price-change alerts (outbox) -----------------------------------------------

@app.get("/api/alerts")
def list_alerts(unseen_only: bool = True):
    """Price-change alerts; by default only unseen ones (the outbox)."""
    conn = get_conn()
    return alerts_mod.list_alerts(conn, unseen_only=unseen_only)


@app.get("/api/alerts/count")
def alert_count():
    """Number of unseen alerts — drives the UI badge."""
    return {"unseen": alerts_mod.unseen_count(get_conn())}


@app.post("/api/alerts/{alert_id}/seen")
def alert_seen(alert_id: int):
    conn = get_conn()
    with conn:
        ok = alerts_mod.mark_seen(conn, alert_id)
    if not ok:
        raise HTTPException(404, "alert not found")
    return {"id": alert_id, "seen": True}


@app.post("/api/alerts/seen-all")
def alerts_seen_all():
    conn = get_conn()
    with conn:
        marked = alerts_mod.mark_all_seen(conn)
    return {"marked": marked}


# --- price history -------------------------------------------------------------

@app.get("/api/subscriptions/{sub_id}/price-history")
def price_history(sub_id: int):
    conn = get_conn()
    if not conn.execute("SELECT 1 FROM subscriptions WHERE id = ?",
                        (sub_id,)).fetchone():
        raise HTTPException(404, "subscription not found")
    rows = conn.execute(
        "SELECT amount, changed_at FROM price_history"
        " WHERE subscription_id = ? ORDER BY changed_at, id",
        (sub_id,)).fetchall()
    return [{"amount": r["amount"], "date": r["changed_at"]} for r in rows]


@app.get("/api/price-changes")
def price_changes():
    """Human-readable price-change summaries ('Netflix: 15.49→16.99 ...')."""
    conn = get_conn()
    return history.price_change_summaries(conn)


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
