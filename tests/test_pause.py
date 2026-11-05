# Pause/unpause: frozen subscriptions stay visible but cost nothing until
# they are counted again.
import datetime as dt

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.remind import collect


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SUBWATCH_DB", str(tmp_path / "sw.db"))
    return TestClient(app)


def _mk(client, name, amount=10.0, **kw):
    body = {"name": name, "amount": amount, "cycle": "monthly",
            "next_due_date": (dt.date.today() + dt.timedelta(days=5)).isoformat()}
    body.update(kw)
    return client.post("/api/subscriptions", json=body).json()


def test_pause_and_unpause_toggle(client):
    sub = _mk(client, "Netflix")
    r = client.post(f"/api/subscriptions/{sub['id']}/pause").json()
    assert r == {"id": sub["id"], "paused": True}
    r = client.post(f"/api/subscriptions/{sub['id']}/unpause").json()
    assert r == {"id": sub["id"], "paused": False}


def test_pause_unknown_id_404(client):
    assert client.post("/api/subscriptions/999/pause").status_code == 404
    assert client.post("/api/subscriptions/999/unpause").status_code == 404


def test_paused_visible_in_list_but_sorted_last(client):
    a = _mk(client, "Active")
    p = _mk(client, "Paused")
    client.post(f"/api/subscriptions/{p['id']}/pause")
    subs = client.get("/api/subscriptions").json()
    assert [s["name"] for s in subs] == ["Active", "Paused"]
    assert [s["paused"] for s in subs] == [False, True]


def test_paused_excluded_from_summary_totals(client):
    a = _mk(client, "Active", amount=10.0)
    p = _mk(client, "Paused", amount=90.0)
    client.post(f"/api/subscriptions/{p['id']}/pause")
    s = client.get("/api/summary").json()
    assert s["active_count"] == 1
    assert s["paused_count"] == 1
    assert s["monthly_by_currency"]["USD"] == 10.0
    assert s["next_due"]["name"] == "Active"


def test_paused_excluded_from_upcoming_and_ics(client):
    p = _mk(client, "Paused")
    a = _mk(client, "Active")
    client.post(f"/api/subscriptions/{p['id']}/pause")
    up = client.get("/api/upcoming").json()
    assert {u["subscription"]["name"] for u in up} == {"Active"}
    ics_text = client.get("/api/export.ics").content.decode("utf-8")
    assert "Active" in ics_text and "Paused" not in ics_text


def test_paused_excluded_from_worst_offenders(client):
    p = _mk(client, "Paused", amount=999.0)
    a = _mk(client, "Active", amount=5.0)
    client.post(f"/api/subscriptions/{p['id']}/pause")
    top = client.get("/api/worst-offenders").json()
    assert [t["name"] for t in top] == ["Active"]


def test_paused_excluded_from_remind_collect(tmp_path, monkeypatch):
    monkeypatch.setenv("SUBWATCH_DB", str(tmp_path / "sw.db"))
    client = TestClient(app)
    p = _mk(client, "Paused")
    client.post(f"/api/subscriptions/{p['id']}/pause")
    charges, _trials = collect(30, str(tmp_path / "sw.db"))
    assert all(r["name"] != "Paused" for _, r in charges)
    assert len(charges) == 0
