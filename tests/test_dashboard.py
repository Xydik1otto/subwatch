# Dashboard widgets: /api/dashboard віддає всі віджети одним викликом
# (summary, upcoming 7д, trials, to-cancel, unseen alerts, worst offenders,
# 3-місячний trend) або вибірково через ?widgets=.
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
            "cycle": "monthly", "next_due_date":
            (dt.date.today() + dt.timedelta(days=3)).isoformat()}
    body.update(overrides)
    r = client.post("/api/subscriptions", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_dashboard_full_set(client):
    sub = _mk(client)
    r = client.get("/api/dashboard")
    assert r.status_code == 200, r.text
    d = r.json()
    assert set(d) == {"summary", "upcoming", "trials", "to_cancel",
                      "unseen_alerts", "worst_offenders", "trends"}
    # summary: одна активна підписка, monthly-equivalent 15.49 USD
    assert d["summary"]["active_count"] == 1
    assert d["summary"]["monthly_by_currency"] == {"USD": 15.49}
    # upcoming: списання за 3 дні у вікні 7 днів
    assert len(d["upcoming"]) == 1
    assert d["upcoming"][0]["kind"] == "charge"
    assert d["upcoming"][0]["subscription"]["id"] == sub["id"]
    # worst offenders: топ-3, тут одна позиція
    assert len(d["worst_offenders"]) == 1
    assert d["worst_offenders"][0]["name"] == "Netflix"
    # trends: 3 місяці, щомісячні списання по 15.49 → mid-window non-empty
    assert len(d["trends"]["months"]) == 3
    assert any(b["totals"].get("USD") == 15.49
               for b in d["trends"]["months"])
    assert d["trends"]["summary"]["per_currency"]["USD"]["monthly_average"] \
        == round(15.49 * sum(1 for b in d["trends"]["months"]
                             if b["totals"].get("USD")) / 3, 2)


def test_dashboard_widget_selection(client):
    _mk(client)
    r = client.get("/api/dashboard", params={"widgets": "summary,trends"})
    assert r.status_code == 200, r.text
    assert set(r.json()) == {"summary", "trends"}
    r = client.get("/api/dashboard", params={"widgets": "unseen_alerts"})
    assert r.json() == {"unseen_alerts": 0}


def test_dashboard_unknown_widget_422(client):
    r = client.get("/api/dashboard", params={"widgets": "summary,nope"})
    assert r.status_code == 422
    assert "nope" in r.json()["detail"]


def test_dashboard_to_cancel_and_alerts(client):
    sub = _mk(client, name="Cancellable",
              next_due_date=(dt.date.today() + dt.timedelta(days=10)).isoformat())
    client.post(f"/api/subscriptions/{sub['id']}/plan-cancel",
                json={"cancel_deadline":
                      (dt.date.today() + dt.timedelta(days=5)).isoformat()})
    # зміна ціни → alert у вхідних (PATCH вимагає повне тіло SubscriptionIn)
    current = client.get("/api/subscriptions").json()[0]
    current["amount"] = 19.99
    r = client.patch(f"/api/subscriptions/{sub['id']}", json=current)
    assert r.status_code == 200, r.text
    d = client.get("/api/dashboard", params={"widgets":
                                             "to_cancel,unseen_alerts"}).json()
    assert d["to_cancel"]["count"] == 1
    assert d["to_cancel"]["nearest_deadline"] == \
        (dt.date.today() + dt.timedelta(days=5)).isoformat()
    assert d["unseen_alerts"] == 1


def test_dashboard_trials_widget(client):
    _mk(client, name="TrialGuy",
        trial_end_date=(dt.date.today() + dt.timedelta(days=2)).isoformat(),
        next_due_date=(dt.date.today() + dt.timedelta(days=30)).isoformat())
    d = client.get("/api/dashboard", params={"widgets": "trials"}).json()
    assert len(d["trials"]) == 1
    assert d["trials"][0]["days_left"] == 2
    assert d["trials"][0]["name"] == "TrialGuy"


def test_dashboard_empty_db(client):
    d = client.get("/api/dashboard").json()
    assert d["summary"]["active_count"] == 0
    assert d["upcoming"] == []
    assert d["trials"] == []
    assert d["to_cancel"] == {"count": 0, "nearest_deadline": None}
    assert d["unseen_alerts"] == 0
    assert d["worst_offenders"] == []
    assert all(b["totals"] == {} for b in d["trends"]["months"])
