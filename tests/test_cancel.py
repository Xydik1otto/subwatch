# Cancellation workflow: plan-cancel with deadline, ICS event, UI badge.
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


def test_plan_cancel_sets_status_and_deadline(client):
    sub = _mk(client)
    r = client.post(f"/api/subscriptions/{sub['id']}/plan-cancel",
                    json={"cancel_deadline": "2024-05-30"})
    assert r.status_code == 200
    body = r.json()
    assert body["cancel_planned"] is True
    assert body["cancel_deadline"] == "2024-05-30"

    row = client.get("/api/subscriptions").json()[0]
    assert row["cancel_planned"] is True
    assert row["cancel_deadline"] == "2024-05-30"


def test_plan_cancel_invalid_date_422(client):
    sub = _mk(client)
    r = client.post(f"/api/subscriptions/{sub['id']}/plan-cancel",
                    json={"cancel_deadline": "2024-02-31"})
    assert r.status_code == 422
    r = client.post(f"/api/subscriptions/{sub['id']}/plan-cancel",
                    json={"cancel_deadline": "not-a-date"})
    assert r.status_code == 422


def test_plan_cancel_unknown_sub_404(client):
    r = client.post("/api/subscriptions/999/plan-cancel",
                    json={"cancel_deadline": "2024-05-30"})
    assert r.status_code == 404


def test_unplan_cancel_clears(client):
    sub = _mk(client)
    client.post(f"/api/subscriptions/{sub['id']}/plan-cancel",
                json={"cancel_deadline": "2024-05-30"})
    r = client.post(f"/api/subscriptions/{sub['id']}/unplan-cancel")
    assert r.status_code == 200
    row = client.get("/api/subscriptions").json()[0]
    assert row["cancel_planned"] is False
    assert row["cancel_deadline"] is None


def test_to_cancel_list_sorted_by_deadline(client):
    a = _mk(client, name="Alpha", next_due_date="2024-06-01")
    b = _mk(client, name="Beta", next_due_date="2024-06-02")
    _mk(client, name="Keeping", next_due_date="2024-06-03")
    client.post(f"/api/subscriptions/{b['id']}/plan-cancel",
                json={"cancel_deadline": "2024-05-20"})
    client.post(f"/api/subscriptions/{a['id']}/plan-cancel",
                json={"cancel_deadline": "2024-05-10"})
    items = client.get("/api/to-cancel").json()
    assert [s["name"] for s in items] == ["Alpha", "Beta"]


def test_deadline_lands_in_ics_export(client):
    sub = _mk(client, next_due_date="2026-11-20")
    client.post(f"/api/subscriptions/{sub['id']}/plan-cancel",
                json={"cancel_deadline": "2026-11-18"})
    data = client.get("/api/export.ics").content.decode()
    assert "CANCEL BEFORE: Netflix" in data
    assert data.count("DTSTART;VALUE=DATE:20261118") == 1
    # unmarked subscriptions do not produce deadline events
    other = _mk(client, name="Keeper", next_due_date="2026-11-20")
    data = client.get("/api/export.ics").content.decode()
    assert data.count("CANCEL BEFORE") == 1
    assert "CANCEL BEFORE: Keeper" not in data


def test_ui_has_tocancel_badge_styles():
    html = TestClient(app).get("/").text
    assert "tocancel" in html
    assert "скасувати до" in html
