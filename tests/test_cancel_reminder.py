# Cancel reminders за N днів до списання: дедлайн виводиться автоматично
# (next_due_date - N), перераховується при mark-paid, список «встигнути
# скасувати» — /api/cancel-reminders?days=N.
import datetime as dt

import pytest
from fastapi.testclient import TestClient

from backend import cancel_reminder
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


# --- pure functions ------------------------------------------------------------

def test_deadline_for_subtracts_days():
    assert cancel_reminder.deadline_for(D(2024, 6, 1), 5) == D(2024, 5, 27)
    assert cancel_reminder.deadline_for(D(2024, 3, 1), 3) == D(2024, 2, 27)


def test_deadline_for_requires_at_least_one_day():
    with pytest.raises(ValueError):
        cancel_reminder.deadline_for(D(2024, 6, 1), 0)
    with pytest.raises(ValueError):
        cancel_reminder.deadline_for(D(2024, 6, 1), -2)


def _row(**over):
    base = {"id": 1, "name": "Netflix", "amount": 15.49, "currency": "USD",
            "next_due_date": "2024-06-01", "cancel_planned": 1,
            "cancel_deadline": "2024-05-27"}
    base.update(over)
    return base


def test_due_reminders_window_and_sorting():
    today = D(2024, 5, 25)
    rows = [
        _row(id=1, name="Beta", cancel_deadline="2024-05-30"),   # 5 днів
        _row(id=2, name="Alpha", cancel_deadline="2024-05-27"),  # 2 дні
        _row(id=3, name="Past", cancel_deadline="2024-05-20"),   # прострочений
        _row(id=4, name="Far", cancel_deadline="2024-06-15"),    # за вікном
        _row(id=5, name="NotPlanned", cancel_planned=0,
             cancel_deadline="2024-05-26"),
        _row(id=6, name="NoDeadline", cancel_planned=1,
             cancel_deadline=None),
    ]
    out = cancel_reminder.due_reminders(rows, today, 7)
    assert [(d["name"], d["days_left"]) for d in out] == [
        ("Alpha", 2), ("Beta", 5)]
    assert out[0]["cancel_deadline"] == "2024-05-27"
    assert out[0]["next_due_date"] == "2024-06-01"


def test_due_reminders_zero_horizon_includes_today():
    rows = [_row(cancel_deadline="2024-05-25")]
    out = cancel_reminder.due_reminders(rows, D(2024, 5, 25), 0)
    assert len(out) == 1 and out[0]["days_left"] == 0


# --- API -----------------------------------------------------------------------

def test_cancel_reminder_computes_deadline(client):
    sub = _mk(client)
    r = client.post(f"/api/subscriptions/{sub['id']}/cancel-reminder",
                    json={"days_before": 5})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["cancel_planned"] is True
    assert body["days_before"] == 5
    # 2024-06-01 - 5 днів
    assert body["cancel_deadline"] == "2024-05-27"
    row = client.get("/api/subscriptions").json()[0]
    assert row["cancel_planned"] is True
    assert row["cancel_deadline"] == "2024-05-27"
    assert row["cancel_days_before"] == 5


def test_cancel_reminder_validation(client):
    sub = _mk(client)
    r = client.post(f"/api/subscriptions/{sub['id']}/cancel-reminder",
                    json={"days_before": 0})
    assert r.status_code == 422
    r = client.post(f"/api/subscriptions/{sub['id']}/cancel-reminder",
                    json={"days_before": 91})
    assert r.status_code == 422


def test_cancel_reminder_unknown_sub_404(client):
    r = client.post("/api/subscriptions/999/cancel-reminder",
                    json={"days_before": 5})
    assert r.status_code == 404


def test_reminder_deadline_rolls_forward_on_mark_paid(client):
    """mark-paid відкочує списання — дедлайн 'N днів до списання' їде за ним."""
    sub = _mk(client, next_due_date="2024-06-01")
    client.post(f"/api/subscriptions/{sub['id']}/cancel-reminder",
                json={"days_before": 5})
    client.post(f"/api/subscriptions/{sub['id']}/mark-paid")
    row = client.get("/api/subscriptions").json()[0]
    assert row["next_due_date"] == "2024-07-01"
    assert row["cancel_deadline"] == "2024-06-26"   # 2024-07-01 - 5 днів


def test_manual_deadline_not_rolled_by_mark_paid(client):
    """Ручний plan-cancel (без days_before) веде себе як раніше: дедлайн
    зафіксований, mark-paid його не рухає."""
    sub = _mk(client, next_due_date="2024-06-01")
    client.post(f"/api/subscriptions/{sub['id']}/plan-cancel",
                json={"cancel_deadline": "2024-05-30"})
    client.post(f"/api/subscriptions/{sub['id']}/mark-paid")
    row = client.get("/api/subscriptions").json()[0]
    assert row["cancel_deadline"] == "2024-05-30"
    assert row["cancel_days_before"] is None


def test_unplan_clears_days_before(client):
    sub = _mk(client)
    client.post(f"/api/subscriptions/{sub['id']}/cancel-reminder",
                json={"days_before": 5})
    client.post(f"/api/subscriptions/{sub['id']}/unplan-cancel")
    row = client.get("/api/subscriptions").json()[0]
    assert row["cancel_planned"] is False
    assert row["cancel_deadline"] is None
    assert row["cancel_days_before"] is None


def test_cancel_reminders_list(client):
    a = _mk(client, name="Alpha", next_due_date="2024-06-01")
    b = _mk(client, name="Beta", next_due_date="2024-06-02")
    _mk(client, name="Keeping", next_due_date="2024-06-03")
    client.post(f"/api/subscriptions/{a['id']}/cancel-reminder",
                json={"days_before": 5})   # 2024-05-27
    client.post(f"/api/subscriptions/{b['id']}/cancel-reminder",
                json={"days_before": 3})   # 2024-05-30
    out = client.get("/api/cancel-reminders", params={
        "days": 7, "today": "2024-05-25"}).json()
    assert [(d["name"], d["days_left"]) for d in out] == [("Alpha", 2), ("Beta", 5)]
    # вузьке вікно — тільки Alpha
    out = client.get("/api/cancel-reminders", params={
        "days": 3, "today": "2024-05-25"}).json()
    assert [d["name"] for d in out] == ["Alpha"]
    # пауза прибирає з нагадувань (списання не буде)
    client.post(f"/api/subscriptions/{b['id']}/pause")
    out = client.get("/api/cancel-reminders", params={
        "days": 7, "today": "2024-05-25"}).json()
    assert [d["name"] for d in out] == ["Alpha"]


def test_cancel_reminders_lands_in_ics(client):
    """Дедлайн з cancel-reminder потрапляє в .ics як подія CANCEL BEFORE."""
    due = dt.date.today() + dt.timedelta(days=30)
    sub = _mk(client, next_due_date=due.isoformat())
    client.post(f"/api/subscriptions/{sub['id']}/cancel-reminder",
                json={"days_before": 5})
    ics_text = client.get("/api/export.ics").text
    assert "CANCEL BEFORE" in ics_text
    assert (due - dt.timedelta(days=5)).strftime("%Y%m%d") in ics_text
