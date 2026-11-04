# API layer: CRUD, sorting, summary, upcoming, trials, ICS export.
import datetime as dt

import pytest
from fastapi.testclient import TestClient

from backend.main import app

D = dt.date


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SUBWATCH_DB", str(tmp_path / "sw.db"))
    return TestClient(app)


def _mk(client, **overrides):
    body = {"name": "Netflix", "amount": 15.49, "currency": "USD",
            "cycle": "monthly", "next_due_date": "2024-06-01"}
    body.update(overrides)
    r = client.post("/api/subscriptions", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_crud_flow(client):
    sub = _mk(client)
    r = client.get("/api/subscriptions")
    assert len(r.json()) == 1

    r = client.patch(f"/api/subscriptions/{sub['id']}",
                     json={**sub, "amount": 19.99})
    assert r.json()["amount"] == 19.99

    r = client.post(f"/api/subscriptions/{sub['id']}/mark-paid")
    assert r.json()["next_due_date"] == "2024-07-01"

    r = client.delete(f"/api/subscriptions/{sub['id']}")
    assert r.json()["deleted"] == sub["id"]
    assert client.get("/api/subscriptions").json() == []

    r = client.delete(f"/api/subscriptions/{sub['id']}")
    assert r.status_code == 404


def test_custom_cycle_validation(client):
    r = client.post("/api/subscriptions", json={
        "name": "Bad", "amount": 5, "cycle": "custom",
        "next_due_date": "2024-06-01"})  # no custom_days
    assert r.status_code == 422


def test_summary_monthly_and_yearly_equivalents(client):
    _mk(client, name="Monthly", amount=10.0, cycle="monthly")
    _mk(client, name="Yearly", amount=120.0, cycle="yearly")
    _mk(client, name="Weekly", amount=5.0, cycle="custom", custom_days=7)
    s = client.get("/api/summary").json()
    assert s["active_count"] == 3
    assert s["monthly_by_currency"]["USD"] == pytest.approx(
        10.0 + 10.0 + 5.0 * 365.25 / 7 / 12, abs=0.01)
    assert s["yearly_by_currency"]["USD"] == pytest.approx(
        (10.0 + 10.0 + 5.0 * 365.25 / 7 / 12) * 12, abs=0.1)


def test_summary_next_due(client):
    _mk(client, name="A", next_due_date="2024-06-10")
    _mk(client, name="B", next_due_date="2024-06-02")
    s = client.get("/api/summary").json()
    assert s["next_due"]["name"] == "B"


def test_upcoming_horizon_and_trial_warning(client):
    today = D.today()
    _mk(client, name="Soon",
        next_due_date=(today + dt.timedelta(days=5)).isoformat())
    _mk(client, name="Far",
        next_due_date=(today + dt.timedelta(days=200)).isoformat())
    _mk(client, name="Trial",
        next_due_date=(today + dt.timedelta(days=400)).isoformat(),
        trial_end_date=(today + dt.timedelta(days=2)).isoformat())

    up = client.get("/api/upcoming", params={"days": 30}).json()
    kinds = {(u["subscription"]["name"], u["kind"]) for u in up}
    assert ("Soon", "charge") in kinds
    assert ("Trial", "trial_end") in kinds
    assert all(name != "Far" for name, _ in kinds)

    trial_item = [u for u in up if u["kind"] == "trial_end"][0]
    assert trial_item["warning"] is True

    trials = client.get("/api/trials").json()
    assert [t["name"] for t in trials] == ["Trial"]
    assert trials[0]["days_left"] == 2


def test_mark_paid_month_end(client):
    sub = _mk(client, name="Gym", cycle="monthly",
              next_due_date="2024-01-31")
    r = client.post(f"/api/subscriptions/{sub['id']}/mark-paid")
    assert r.json()["next_due_date"] == "2024-02-29"  # leap year clamp


def test_ics_export_endpoint(client):
    _mk(client, name="Netflix", next_due_date="2024-06-01")
    r = client.get("/api/export.ics")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/calendar")
    text = r.content.decode("utf-8")
    assert text.startswith("BEGIN:VCALENDAR")
    assert "SUMMARY:Charge: Netflix (15.49 USD)" in text


def test_index_page_served(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "subwatch" in r.text.lower()
