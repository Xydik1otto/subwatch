# Alpha API surface: CSV import endpoints, price history, cost-per-use.
import datetime as dt

import pytest
from fastapi.testclient import TestClient

from backend.db import connect
from backend.history import format_change
from backend.main import app

D = dt.date


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SUBWATCH_DB", str(tmp_path / "sw.db"))
    return TestClient(app)


def _csv(*rows: str) -> str:
    return "\n".join(("date,description,amount",) + tuple(rows))


def test_import_analyze_finds_candidates(client):
    csv_text = _csv("2026-01-01,Netflix,15.49",
                    "2026-02-01,Netflix,15.49",
                    "2026-03-01,Netflix,15.49",
                    "2026-04-01,Netflix,15.49")
    r = client.post("/api/import/analyze", json={"csv": csv_text})
    assert r.status_code == 200
    data = r.json()
    assert data["parsed_rows"] == 4
    assert len(data["candidates"]) == 1
    c = data["candidates"][0]
    assert c["name"] == "Netflix" and c["amount"] == 15.49
    assert c["cycle"] == "monthly" and c["next_due_date"] == "2026-05-01"


def test_import_analyze_rejects_garbage(client):
    r = client.post("/api/import/analyze", json={"csv": "hello\nworld\n"})
    assert r.status_code == 422


def test_import_confirm_creates_subscriptions(client):
    r = client.post("/api/import/confirm", json={"candidates": [{
        "name": "Netflix", "amount": 15.49, "cycle": "monthly",
        "next_due_date": "2026-05-01", "description": "NETFLIX.COM 8812"}]})
    assert r.status_code == 200
    created = r.json()["created"]
    assert len(created) == 1
    sub = created[0]
    assert sub["name"] == "Netflix" and sub["amount"] == 15.49
    assert "NETFLIX.COM" in sub["notes"]
    # imported subscriptions get a first price-history point too
    hist = client.get(f"/api/subscriptions/{sub['id']}/price-history").json()
    assert hist == [{"amount": 15.49, "date": dt.date.today().isoformat()}]
    subs = client.get("/api/subscriptions").json()
    assert [s["name"] for s in subs] == ["Netflix"]


def test_price_history_recorded_on_create_and_update(client):
    sub = client.post("/api/subscriptions", json={
        "name": "Netflix", "amount": 15.49, "cycle": "monthly",
        "next_due_date": "2026-06-01"}).json()
    client.patch(f"/api/subscriptions/{sub['id']}", json={
        "name": "Netflix", "amount": 16.99, "cycle": "monthly",
        "next_due_date": "2026-06-01"})
    # same-amount edit must NOT add a duplicate history point
    client.patch(f"/api/subscriptions/{sub['id']}", json={
        "name": "Netflix", "amount": 16.99, "cycle": "monthly",
        "next_due_date": "2026-07-01"})
    hist = client.get(f"/api/subscriptions/{sub['id']}/price-history").json()
    assert [h["amount"] for h in hist] == [15.49, 16.99]


def test_price_history_endpoint_404(client):
    assert client.get("/api/subscriptions/999/price-history").status_code == 404


def test_price_change_summary_text(tmp_path, monkeypatch, client):
    monkeypatch.setenv("SUBWATCH_DB", str(tmp_path / "sw.db"))
    sub = client.post("/api/subscriptions", json={
        "name": "Netflix", "amount": 15.49, "cycle": "monthly",
        "next_due_date": "2026-11-01"}).json()
    # deterministic history: 2026-03-01 -> 2026-11-01 is 8 months
    conn = connect(str(tmp_path / "sw.db"))
    with conn:
        conn.execute("DELETE FROM price_history WHERE subscription_id = ?",
                     (sub["id"],))
        conn.execute("INSERT INTO price_history(subscription_id, amount, changed_at)"
                     " VALUES (?,?,?)", (sub["id"], 15.49, "2026-03-01"))
        conn.execute("INSERT INTO price_history(subscription_id, amount, changed_at)"
                     " VALUES (?,?,?)", (sub["id"], 16.99, "2026-11-01"))
    summaries = client.get("/api/price-changes").json()
    assert len(summaries) == 1
    change = summaries[0]["changes"][-1]
    assert change["text"] == "Netflix: 15.49→16.99 (+9.7% за 8 міс)"
    assert change["pct"] == pytest.approx(9.7, abs=0.05)
    assert change["months"] == 8


def test_price_change_skips_single_point(client):
    client.post("/api/subscriptions", json={
        "name": "Solo", "amount": 5.0, "cycle": "monthly",
        "next_due_date": "2026-06-01"})
    assert client.get("/api/price-changes").json() == []


def test_format_change_negative_pct():
    text = format_change("X", 20.0, 18.0, 3)
    assert text == "X: 20.00→18.00 (-10.0% за 3 міс)"


def test_cost_per_use(client):
    client.post("/api/subscriptions", json={
        "name": "Gym", "amount": 30.0, "cycle": "monthly",
        "next_due_date": "2026-06-01", "times_used_per_month": 12})
    client.post("/api/subscriptions", json={
        "name": "NoUses", "amount": 10.0, "cycle": "monthly",
        "next_due_date": "2026-06-01"})
    subs = {s["name"]: s for s in client.get("/api/subscriptions").json()}
    assert subs["Gym"]["cost_per_use"] == pytest.approx(2.5)
    assert subs["NoUses"]["cost_per_use"] is None


def test_cost_per_use_weekly_cycle_and_zero_rejected(client):
    r = client.post("/api/subscriptions", json={
        "name": "Bad", "amount": 5.0, "cycle": "monthly",
        "next_due_date": "2026-06-01", "times_used_per_month": -1})
    assert r.status_code == 422
    sub = client.post("/api/subscriptions", json={
        "name": "Weekly", "amount": 10.0, "cycle": "custom", "custom_days": 7,
        "next_due_date": "2026-06-01", "times_used_per_month": 8}).json()
    me = 10.0 * 365.25 / 7 / 12
    assert sub["cost_per_use"] == pytest.approx(me / 8, abs=0.001)
