# Cancel assistant: static knowledge base of the top-20 services.
import pytest
from fastapi.testclient import TestClient

from backend import cancel_kb
from backend.main import app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SUBWATCH_DB", str(tmp_path / "sw.db"))
    return TestClient(app)


def _mk(client, name="Netflix"):
    r = client.post("/api/subscriptions", json={
        "name": name, "amount": 15.49, "currency": "USD",
        "cycle": "monthly", "next_due_date": "2024-06-01"})
    assert r.status_code == 200, r.text
    return r.json()


def test_kb_has_top20_services():
    services = cancel_kb.all_services()
    assert len(services) == 20
    names = {s["name"] for s in services}
    # services named in the research: Netflix, Spotify... must be covered
    for expected in ("Netflix", "Spotify", "YouTube Premium", "Disney+",
                     "Amazon Prime", "Adobe Creative Cloud", "ChatGPT Plus"):
        assert expected in names


def test_every_service_has_url_and_bilingual_steps():
    for sid in cancel_kb.SERVICES:
        g = cancel_kb.guide(sid)
        assert g["cancel_url"].startswith("https://")
        assert len(g["steps_uk"]) >= 3
        assert len(g["steps_en"]) >= 3
        assert g["steps_uk"] != g["steps_en"]


def test_catalogue_endpoint(client):
    r = client.get("/api/cancel-assistant")
    assert r.status_code == 200
    services = r.json()
    assert len(services) == 20
    assert all({"id", "name", "cancel_url"} <= set(s) for s in services)
    # stable, alphabetical order for the UI list
    names = [s["name"] for s in services]
    assert names == sorted(names, key=str.lower)


def test_guide_endpoint_bilingual(client):
    r = client.get("/api/cancel-assistant/netflix")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "Netflix"
    assert body["cancel_url"] == "https://www.netflix.com/cancelplan"
    assert body["steps_uk"] and body["steps_en"]


def test_guide_unknown_404(client):
    assert client.get("/api/cancel-assistant/not-a-service").status_code == 404


def test_subscription_matches_known_service(client):
    sub = _mk(client, name="Netflix Premium 4K")
    r = client.get(f"/api/subscriptions/{sub['id']}/cancel-guide")
    assert r.status_code == 200
    body = r.json()
    assert body["service_id"] == "netflix"
    assert body["cancel_url"].startswith("https://www.netflix.com")


def test_subscription_match_prefers_longer_keyword(client):
    sub = _mk(client, name="YouTube Premium")
    body = client.get(f"/api/subscriptions/{sub['id']}/cancel-guide").json()
    assert body["service_id"] == "youtube-premium"


def test_subscription_unknown_service_404(client):
    sub = _mk(client, name="Дядиний хостинг ТзОВ")
    r = client.get(f"/api/subscriptions/{sub['id']}/cancel-guide")
    assert r.status_code == 404
    assert "no cancel-assistant guide" in r.json()["detail"]


def test_cancel_guide_unknown_sub_404(client):
    assert client.get("/api/subscriptions/999/cancel-guide").status_code == 404


def test_match_service_case_insensitive():
    assert cancel_kb.match_service("My NETFLIX plan") == "netflix"
    assert cancel_kb.match_service("spotify family") == "spotify"
    assert cancel_kb.match_service("random thing") is None


def test_all_urls_are_official_https_domains():
    for svc in cancel_kb.SERVICES.values():
        assert svc["url"].startswith("https://")
        # no third-party aggregators, only official domains
        assert "cancelon" not in svc["url"] and "wiki" not in svc["url"]
