# Family mode: owner / payer / share_pct on subscriptions + /api/family.
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


def test_create_with_family_fields(client):
    sub = _mk(client, owner="Оля", payer="Тарас", share_pct=50)
    assert sub["owner"] == "Оля"
    assert sub["payer"] == "Тарас"
    assert sub["share_pct"] == 50


def test_defaults_are_personal(client):
    sub = _mk(client)
    assert sub["owner"] is None
    assert sub["payer"] is None
    assert sub["share_pct"] == 100


def test_share_pct_bounds(client):
    r = client.post("/api/subscriptions", json={
        "name": "Bad", "amount": 5, "cycle": "monthly",
        "next_due_date": "2024-06-01", "share_pct": 150})
    assert r.status_code == 422
    r = client.post("/api/subscriptions", json={
        "name": "Bad", "amount": 5, "cycle": "monthly",
        "next_due_date": "2024-06-01", "share_pct": -1})
    assert r.status_code == 422


def test_patch_updates_family_fields(client):
    sub = _mk(client)
    r = client.patch(f"/api/subscriptions/{sub['id']}", json={
        "name": "Netflix", "amount": 15.49, "currency": "USD",
        "cycle": "monthly", "next_due_date": "2024-06-01",
        "owner": "Діти", "payer": "Мама", "share_pct": 100})
    body = r.json()
    assert body["owner"] == "Діти"
    assert body["payer"] == "Мама"


def test_family_breakdown_groups_by_payer_with_share(client):
    _mk(client, name="Netflix", amount=15.49, payer="Тарас", owner="Сім'я")
    _mk(client, name="Spotify", amount=10.99, payer="Тарас")
    _mk(client, name="iCloud", amount=2.99, payer="Оля", owner="Оля", share_pct=50)
    _mk(client, name="Дешевий VPS", amount=4.00)   # без платника
    data = client.get("/api/family").json()
    payers = {p["payer"]: p for p in data["payers"]}
    assert set(payers) == {"Тарас", "Оля", "(не вказано)"}
    assert payers["Тарас"]["monthly_by_currency"] == {"USD": 26.48}
    assert payers["Тарас"]["yearly_by_currency"] == {"USD": 317.76}
    assert payers["Тарас"]["subscription_count"] == 2
    # share_pct applied: 2.99 * 50% = 1.50 (rounded 1.5)
    assert payers["Оля"]["monthly_by_currency"] == {"USD": 1.5}
    assert payers["Оля"]["subscriptions"][0]["share_pct"] == 50
    assert payers["Оля"]["subscriptions"][0]["owner"] == "Оля"
    # uncategorised bucket
    assert payers["(не вказано)"]["subscription_count"] == 1


def test_family_separates_currencies(client):
    _mk(client, name="Netflix", amount=15.49, currency="USD", payer="Тарас")
    _mk(client, name="Kyivstar", amount=150, currency="UAH", payer="Тарас")
    data = client.get("/api/family").json()
    p = data["payers"][0]
    assert p["monthly_by_currency"] == {"UAH": 150.0, "USD": 15.49}
    assert p["yearly_by_currency"] == {"UAH": 1800.0, "USD": 185.88}


def test_family_excludes_deleted(client):
    sub = _mk(client, payer="Тарас")
    client.delete(f"/api/subscriptions/{sub['id']}")
    data = client.get("/api/family").json()
    assert data["payers"] == []


def test_family_includes_paused_with_flag_visible(client):
    sub = _mk(client, payer="Тарас")
    client.post(f"/api/subscriptions/{sub['id']}/pause")
    data = client.get("/api/family").json()
    assert data["payers"][0]["subscription_count"] == 1


def test_ui_has_payer_column():
    html = TestClient(app).get("/").text
    # 'Хто платить' тепер у i18n-словнику (col.payer)
    import json
    from pathlib import Path
    uk = json.loads((Path(__file__).parent.parent / "static" / "i18n" / "uk.json")
                    .read_text(encoding="utf-8"))
    assert uk["col.payer"] == "Хто платить"
    assert "share_pct" in html
