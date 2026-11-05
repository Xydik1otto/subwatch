# Price-change alerts (outbox): alert on every amount change, unseen badge.
import pytest
from fastapi.testclient import TestClient

from backend.main import app


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


def _patch_amount(client, sub_id, amount, name="Netflix"):
    return client.patch(f"/api/subscriptions/{sub_id}", json={
        "name": name, "amount": amount, "currency": "USD",
        "cycle": "monthly", "next_due_date": "2024-06-01"})


def test_amount_change_creates_alert(client):
    sub = _mk(client)
    assert client.get("/api/alerts").json() == []
    _patch_amount(client, sub["id"], 17.99)
    alerts = client.get("/api/alerts").json()
    assert len(alerts) == 1
    a = alerts[0]
    assert a["subscription_id"] == sub["id"]
    assert a["old_amount"] == 15.49
    assert a["new_amount"] == 17.99
    assert a["currency"] == "USD"
    assert a["seen"] is False
    assert a["direction"] == "up"
    assert a["pct"] == 16.1  # +2.50/15.49
    assert "Netflix" in a["text"] and "15.49" in a["text"] and "17.99" in a["text"]


def test_same_amount_no_alert(client):
    sub = _mk(client)
    _patch_amount(client, sub["id"], 15.49)
    assert client.get("/api/alerts").json() == []


def test_decrease_alert_marks_direction_down(client):
    sub = _mk(client)
    _patch_amount(client, sub["id"], 9.99)
    a = client.get("/api/alerts").json()[0]
    assert a["direction"] == "down"
    assert a["pct"] < 0


def test_unseen_only_filter_and_seen_flow(client):
    sub = _mk(client)
    _patch_amount(client, sub["id"], 17.99)
    alert_id = client.get("/api/alerts").json()[0]["id"]
    # seen alerts disappear from the default (outbox) view
    assert client.get("/api/alerts?unseen_only=true").json()
    r = client.post(f"/api/alerts/{alert_id}/seen")
    assert r.status_code == 200 and r.json()["seen"] is True
    assert client.get("/api/alerts").json() == []
    # ...but remain in the full history
    full = client.get("/api/alerts?unseen_only=false").json()
    assert len(full) == 1 and full[0]["seen"] is True


def test_seen_unknown_alert_404(client):
    assert client.post("/api/alerts/999/seen").status_code == 404


def test_seen_all_marks_everything(client):
    a = _mk(client, name="A")
    b = _mk(client, name="B")
    _patch_amount(client, a["id"], 20.0, name="A")
    _patch_amount(client, b["id"], 25.0, name="B")
    r = client.post("/api/alerts/seen-all")
    assert r.json()["marked"] == 2
    assert client.get("/api/alerts").json() == []


def test_alert_count_endpoint(client):
    sub = _mk(client)
    assert client.get("/api/alerts/count").json() == {"unseen": 0}
    _patch_amount(client, sub["id"], 19.99)
    assert client.get("/api/alerts/count").json() == {"unseen": 1}


def test_delete_subscription_removes_its_alerts(client):
    sub = _mk(client)
    _patch_amount(client, sub["id"], 19.99)
    assert len(client.get("/api/alerts").json()) == 1
    client.delete(f"/api/subscriptions/{sub['id']}")
    assert client.get("/api/alerts").json() == []


def test_ui_has_alert_badge_and_price_mark():
    html = TestClient(app).get("/").text
    assert 'id="alert-badge"' in html
    assert "loadAlerts" in html
    assert "price-mark" in html
    assert "/api/alerts" in html
