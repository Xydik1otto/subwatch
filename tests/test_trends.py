# Spending trends по місяцях: фактичні списання за останні N місяців
# (backend/trends.py + GET /api/trends). Дзеркальний до projection тестовий
# набір: помісячні бакети, пропущені цикли, пауза, змішані валюти, тренд.
import datetime as dt

import pytest
from fastapi.testclient import TestClient

from backend import trends
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


# --- pure functions -------------------------------------------------------------

def test_bucket_labels_walks_back():
    assert trends.bucket_labels(D(2026, 11, 5), 3) == ["2026-09", "2026-10", "2026-11"]
    assert trends.bucket_labels(D(2026, 1, 31), 3) == ["2025-11", "2025-12", "2026-01"]


def test_previous_due_monthly_yearly_custom():
    assert trends.previous_due(D(2024, 3, 31), "monthly", None, 31) == D(2024, 2, 29)
    assert trends.previous_due(D(2024, 3, 1), "monthly", None, 1) == D(2024, 2, 1)
    assert trends.previous_due(D(2024, 3, 1), "yearly", None, 1) == D(2023, 3, 1)
    assert trends.previous_due(D(2024, 3, 11), "custom", 7) == D(2024, 3, 4)
    with pytest.raises(ValueError):
        trends.previous_due(D(2024, 3, 1), "weekly", None)


def test_past_occurrences_monthly():
    # monthly зі списанням 10-го: 4 дати у вікні з 1 серпня по 30 листопада
    out = trends.past_occurrences(D(2024, 12, 10), "monthly", None,
                                  D(2024, 8, 1), D(2024, 11, 30), 10)
    assert [d.isoformat() for d in out] == [
        "2024-08-10", "2024-09-10", "2024-10-10", "2024-11-10"]


def test_past_occurrences_excludes_today_and_future():
    out = trends.past_occurrences(D(2024, 11, 10), "monthly", None,
                                  D(2024, 8, 1), D(2024, 11, 10), 10)
    # 2024-11-10 — це today, ще не списали; останнє включене — жовтень
    assert [d.isoformat() for d in out] == ["2024-08-10", "2024-09-10", "2024-10-10"]


def test_past_occurrences_custom_weekly():
    out = trends.past_occurrences(D(2024, 3, 29), "custom", 7,
                                  D(2024, 3, 1), D(2024, 3, 31))
    assert [d.isoformat() for d in out] == [
        "2024-03-01", "2024-03-08", "2024-03-15", "2024-03-22", "2024-03-29"]


def test_monthly_trends_totals_per_currency():
    rows = [
        {"name": "A", "amount": 10.0, "currency": "USD", "cycle": "monthly",
         "custom_days": None, "anchor_day": 10, "next_due_date": "2024-12-10",
         "paused": 0},
        {"name": "B", "amount": 5.0, "currency": "EUR", "cycle": "monthly",
         "custom_days": None, "anchor_day": 10, "next_due_date": "2024-12-10",
         "paused": 0},
        {"name": "Paused", "amount": 99.0, "currency": "USD", "cycle": "monthly",
         "custom_days": None, "anchor_day": 10, "next_due_date": "2024-12-10",
         "paused": 1},
    ]
    out = trends.monthly_trends(rows, D(2024, 11, 30), 3)
    assert [b["month"] for b in out] == ["2024-09", "2024-10", "2024-11"]
    assert out == [
        {"month": "2024-09", "totals": {"EUR": 5.0, "USD": 10.0}},
        {"month": "2024-10", "totals": {"EUR": 5.0, "USD": 10.0}},
        {"month": "2024-11", "totals": {"EUR": 5.0, "USD": 10.0}},
    ]


def test_monthly_trends_assumes_recurrence_extends_back():
    """Модель має тільки next_due_date, тож повторюваність продовжується
    й назад у минуле: три місяці по 10.0, поки вікно не вичерпається."""
    rows = [{"name": "A", "amount": 10.0, "currency": "USD", "cycle": "monthly",
             "custom_days": None, "anchor_day": 15, "next_due_date": "2024-12-15",
             "paused": 0}]
    out = trends.monthly_trends(rows, D(2024, 11, 30), 3)
    assert out == [
        {"month": "2024-09", "totals": {"USD": 10.0}},
        {"month": "2024-10", "totals": {"USD": 10.0}},
        {"month": "2024-11", "totals": {"USD": 10.0}},
    ]


def test_monthly_trends_gaps_outside_window():
    """Річна підписка: у вікні 4 місяців лише один місяць зі списанням."""
    rows = [{"name": "Y", "amount": 120.0, "currency": "USD", "cycle": "yearly",
             "custom_days": None, "anchor_day": 10, "next_due_date": "2026-03-10",
             "paused": 0}]
    out = trends.monthly_trends(rows, D(2026, 3, 31), 4)
    months = {b["month"]: b["totals"] for b in out}
    assert months["2026-03"] == {"USD": 120.0}
    assert sum(1 for b in out if b["totals"]) == 1


def test_monthly_trends_empty():
    assert trends.monthly_trends([], D(2024, 11, 30), 3) == [
        {"month": "2024-09", "totals": {}},
        {"month": "2024-10", "totals": {}},
        {"month": "2024-11", "totals": {}},
    ]


def test_trend_summary_directions():
    trends_list = [
        {"month": "2024-09", "totals": {"USD": 10.0}},
        {"month": "2024-10", "totals": {"USD": 10.0}},
        {"month": "2024-11", "totals": {"USD": 15.0}},   # +50% проти середнього
    ]
    s = trends.trend_summary(trends_list)
    usd = s["per_currency"]["USD"]
    assert usd["window_total"] == 35.0
    assert usd["monthly_average"] == round(35 / 3, 2)
    assert usd["last_month"] == 15.0
    assert usd["direction"] == "up"

    flat = trends.trend_summary([
        {"month": "2024-09", "totals": {"USD": 10.0}},
        {"month": "2024-10", "totals": {"USD": 10.5}},
    ])
    assert flat["per_currency"]["USD"]["direction"] == "flat"

    down = trends.trend_summary([
        {"month": "2024-09", "totals": {"USD": 20.0}},
        {"month": "2024-10", "totals": {"USD": 5.0}},
    ])
    assert down["per_currency"]["USD"]["direction"] == "down"

    empty = trends.trend_summary([])
    assert empty["per_currency"] == {}


# --- API -------------------------------------------------------------------------

def test_api_trends_endpoint(client):
    # списання 10-го кожного місяця; вікно 3 місяці до 2024-11-30
    _mk(client, name="A", amount=10.0, next_due_date="2024-12-10",
        anchor_day=10)
    r = client.get("/api/trends", params={"months": 3, "today": "2024-11-30"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert [b["month"] for b in body["months"]] == [
        "2024-09", "2024-10", "2024-11"]
    assert body["primary_currency"] == "USD"
    assert body["summary"]["per_currency"]["USD"]["monthly_average"] == 10.0


def test_api_trends_validation(client):
    r = client.get("/api/trends", params={"months": 0})
    assert r.status_code == 422
    r = client.get("/api/trends", params={"months": 37})
    assert r.status_code == 422


def test_api_trends_empty_db(client):
    r = client.get("/api/trends", params={"months": 2, "today": "2024-11-30"})
    assert r.status_code == 200, r.text
    assert r.json()["primary_currency"] is None
    assert r.json()["summary"]["per_currency"] == {}


def test_api_trends_ignores_paused_and_inactive(client):
    sub = _mk(client, name="A", amount=10.0, next_due_date="2024-12-10",
              anchor_day=10)
    b = _mk(client, name="B", amount=77.0, next_due_date="2024-12-10",
            anchor_day=10)
    client.delete(f"/api/subscriptions/{b['id']}")   # inactive
    client.post(f"/api/subscriptions/{sub['id']}/pause")
    r = client.get("/api/trends", params={"months": 3, "today": "2024-11-30"})
    months = r.json()["months"]
    assert all(m["totals"] == {} for m in months)
