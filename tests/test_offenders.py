# Dashboard: worst offenders (top-N by monthly equivalent).
import pytest
from fastapi.testclient import TestClient

from backend.main import app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SUBWATCH_DB", str(tmp_path / "sw.db"))
    return TestClient(app)


def _mk(client, name, amount, cycle="monthly", ccy="USD", **kw):
    body = {"name": name, "amount": amount, "currency": ccy, "cycle": cycle,
            "next_due_date": "2026-06-01"}
    body.update(kw)
    return client.post("/api/subscriptions", json=body).json()


def test_worst_offenders_sorted_by_monthly_equivalent(client):
    _mk(client, "Small", 2.0)
    _mk(client, "Yearly", 240.0, cycle="yearly")     # 20.0/mo
    _mk(client, "Weekly", 10.0, cycle="custom", custom_days=7)  # ~43.4/mo
    _mk(client, "Big", 50.0)
    top = client.get("/api/worst-offenders").json()
    assert [t["name"] for t in top] == ["Big", "Weekly", "Yearly", "Small"]


def test_worst_offenders_default_limit_five(client):
    for i in range(7):
        _mk(client, f"Sub{i}", float(i + 1))
    top = client.get("/api/worst-offenders").json()
    assert len(top) == 5
    assert top[0]["name"] == "Sub6" and top[-1]["name"] == "Sub2"


def test_worst_offenders_custom_limit(client):
    for i in range(4):
        _mk(client, f"Sub{i}", float(i + 1))
    assert len(client.get("/api/worst-offenders", params={"limit": 2}).json()) == 2
    assert len(client.get("/api/worst-offenders", params={"limit": 0}).json()) == 0


def test_worst_offenders_share_within_currency(client):
    _mk(client, "A", 30.0)
    _mk(client, "B", 10.0)
    _mk(client, "E", 40.0, ccy="EUR")
    top = client.get("/api/worst-offenders").json()
    by_name = {t["name"]: t for t in top}
    # USD total = 40 -> A holds 75%, B 25%; EUR is never mixed in
    assert by_name["A"]["share_of_currency_monthly_pct"] == 75.0
    assert by_name["B"]["share_of_currency_monthly_pct"] == 25.0
    assert by_name["E"]["share_of_currency_monthly_pct"] == 100.0


def test_worst_offenders_empty(client):
    assert client.get("/api/worst-offenders").json() == []
