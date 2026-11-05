# Data safety: one-click export (JSON/CSV) + delete confirmation in UI.
import csv
import io

import pytest
from fastapi.testclient import TestClient

from backend.main import app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SUBWATCH_DB", str(tmp_path / "sw.db"))
    return TestClient(app)


def _mk(client, name="Netflix", amount=15.49):
    r = client.post("/api/subscriptions", json={
        "name": name, "amount": amount, "currency": "USD",
        "cycle": "monthly", "next_due_date": "2024-06-01"})
    assert r.status_code == 200, r.text
    return r.json()


def test_export_json_contains_all_sections(client):
    sub = _mk(client)
    client.patch(f"/api/subscriptions/{sub['id']}", json={
        "name": "Netflix", "amount": 19.99, "currency": "USD",
        "cycle": "monthly", "next_due_date": "2024-06-01"})   # + alert
    data = client.get("/api/export.json").json()
    assert "exported_at" in data
    assert len(data["subscriptions"]) == 1
    assert len(data["price_history"]) == 2
    assert len(data["alerts"]) == 1
    assert data["subscriptions"][0]["name"] == "Netflix"


def test_export_json_includes_family_fields(client):
    _mk(client, name="Fam")
    client.patch("/api/subscriptions/1", json={
        "name": "Fam", "amount": 15.49, "currency": "USD",
        "cycle": "monthly", "next_due_date": "2024-06-01",
        "owner": "Оля", "payer": "Тарас", "share_pct": 50})
    sub = client.get("/api/export.json").json()["subscriptions"][0]
    assert sub["payer"] == "Тарас" and sub["share_pct"] == 50


def test_export_csv_content_type_and_header(client):
    _mk(client)
    r = client.get("/api/export.csv")
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]
    assert "attachment" in r.headers["content-disposition"]
    rows = list(csv.DictReader(io.StringIO(r.content.decode("utf-8"))))
    assert rows[0]["name"] == "Netflix"
    assert rows[0]["amount"] == "15.49"


def test_export_csv_empty_db_has_header(client):
    r = client.get("/api/export.csv")
    assert r.status_code == 200
    assert "id" in r.text and "name" in r.text


def test_export_ics_still_works(client):
    _mk(client)
    assert "BEGIN:VCALENDAR" in client.get("/api/export.ics").text


def test_ui_has_export_links_and_delete_warning():
    html = TestClient(app).get("/").text
    assert "/api/export.json" in html
    assert "/api/export.csv" in html
    # попередження при видаленні: confirm() перед DELETE
    assert "confirm(" in html
    assert "method: 'DELETE'" in html
    assert "data-del" in html
