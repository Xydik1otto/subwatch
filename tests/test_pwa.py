# PWA: /api/today endpoint, manifest + service worker wiring.
import datetime as dt

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


def test_today_returns_charge_due_today(client):
    today = dt.date.today().isoformat()
    _mk(client, name="Due", next_due_date=today)
    _mk(client, name="Later", next_due_date="2099-01-01")
    items = client.get("/api/today").json()
    assert [s["name"] for s in items] == ["Due"]


def test_today_includes_trial_ending_today(client):
    today = dt.date.today().isoformat()
    _mk(client, name="Trial", next_due_date="2099-01-01", trial_end_date=today)
    items = client.get("/api/today").json()
    assert [s["name"] for s in items] == ["Trial"]


def test_today_excludes_paused(client):
    today = dt.date.today().isoformat()
    sub = _mk(client, next_due_date=today)
    client.post(f"/api/subscriptions/{sub['id']}/pause")
    assert client.get("/api/today").json() == []


def test_manifest_and_service_worker_served():
    r = TestClient(app).get("/static/manifest.webmanifest")
    assert r.status_code == 200
    manifest = r.json()
    assert manifest["name"] and manifest["start_url"] == "/"
    assert any("/static/favicon.svg" == i["src"] for i in manifest["icons"])

    r = TestClient(app).get("/static/sw.js")
    assert r.status_code == 200
    assert b"showNotification" in r.content


def test_index_registers_sw_and_manifest():
    html = TestClient(app).get("/").text
    assert 'rel="manifest"' in html
    assert "serviceWorker.register" in html
    assert "/api/today" in html
