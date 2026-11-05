# First-run demo: opt-in demo data on an empty database.
import datetime as dt

import pytest
from fastapi.testclient import TestClient

from backend import demo
from backend.main import app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SUBWATCH_DB", str(tmp_path / "sw.db"))
    return TestClient(app)


def test_seed_creates_demo_data(client):
    assert client.get("/api/subscriptions").json() == []
    r = client.post("/api/demo/seed")
    assert r.status_code == 200
    body = r.json()
    assert body["already_had_data"] is False
    assert len(body["created"]) == len(demo.DEMO_SUBSCRIPTIONS)
    subs = client.get("/api/subscriptions").json()
    names = [s["name"] for s in subs]
    assert "Netflix" in names and "Kyivstar" in names
    netflix = next(s for s in subs if s["name"] == "Netflix")
    assert netflix["payer"] == "Тарас"
    assert netflix["tags"] == "video"


def test_seed_is_idempotent(client):
    first = client.post("/api/demo/seed").json()
    second = client.post("/api/demo/seed").json()
    assert second["created"] == []
    assert second["already_had_data"] is True
    # nothing duplicated
    assert len(client.get("/api/subscriptions").json()) == len(first["created"])


def test_seed_skipped_when_user_has_own_data(client):
    client.post("/api/subscriptions", json={
        "name": "My real sub", "amount": 5, "cycle": "monthly",
        "next_due_date": "2024-06-01"})
    r = client.post("/api/demo/seed").json()
    assert r["already_had_data"] is True
    assert len(client.get("/api/subscriptions").json()) == 1


def test_seed_records_price_history(client):
    client.post("/api/demo/seed")
    hist = client.get("/api/subscriptions/1/price-history").json()
    assert len(hist) == 1
    assert hist[0]["amount"] == demo.DEMO_SUBSCRIPTIONS[0][1]


def test_demo_subscription_with_trial(client):
    client.post("/api/demo/seed")
    subs = client.get("/api/subscriptions").json()
    prime = next(s for s in subs if "Prime" in s["name"])
    assert prime["trial_end_date"] is not None


def test_ui_has_demo_banner():
    html = TestClient(app).get("/").text
    assert 'id="demo-banner"' in html
    assert "/api/demo/seed" in html
    assert 'id="demo-seed"' in html
