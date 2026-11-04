# ICS generation: RFC 5545 shape, CRLF, stable UIDs, escaping.
import datetime as dt

from backend.ics import build_ics, subscription_events

D = dt.date


def _sub(i, name, amount=9.99, ccy="USD", cycle="monthly", custom_days=None,
         due=D(2024, 6, 1), trial=None):
    # sqlite3.Row-like dict access
    return {"id": i, "name": name, "amount": amount, "currency": ccy,
            "cycle": cycle, "custom_days": custom_days,
            "next_due_date": due.isoformat(),
            "trial_end_date": trial.isoformat() if trial else None,
            "notes": None, "tags": None}


def _parse(text: bytes) -> list[str]:
    return text.decode("utf-8").split("\r\n")


def test_ics_basic_structure():
    events = subscription_events([_sub(1, "Netflix")], horizon_days=90, today=D(2024, 5, 20))
    assert len(events) >= 1
    data = build_ics(events)
    lines = _parse(data)
    assert lines[0] == "BEGIN:VCALENDAR"
    assert lines[-2] == "END:VCALENDAR"
    assert "BEGIN:VEVENT" in lines and "END:VEVENT" in lines
    assert any(l.startswith("VERSION:2.0") for l in lines)
    assert any(l.startswith("PRODID:") for l in lines)


def test_ics_event_fields_and_date_format():
    ev = subscription_events([_sub(1, "Netflix", 15.49, "EUR")], horizon_days=30, today=D(2024, 5, 20))[0]
    data = build_ics([ev])
    lines = _parse(data)
    assert f"DTSTART;VALUE=DATE:{D(2024, 6, 1).strftime('%Y%m%d')}" in lines
    assert f"DTEND;VALUE=DATE:{D(2024, 6, 2).strftime('%Y%m%d')}" in lines
    assert any("SUMMARY:Charge: Netflix (15.49 EUR)" in l for l in lines)


def test_ics_uid_stable_and_contains_sub_id_and_date():
    ev = subscription_events([_sub(7, "Spotify")], horizon_days=30, today=D(2024, 5, 20))[0]
    lines = _parse(build_ics([ev]))
    uid = [l for l in lines if l.startswith("UID:")][0]
    assert uid == "UID:subwatch-7-2024-06-01-0@local"


def test_ics_escaping_comma_semicolon():
    ev = subscription_events([_sub(1, "Adobe, CC; full")], horizon_days=30, today=D(2024, 5, 20))[0]
    lines = _parse(build_ics([ev]))
    assert any(l.startswith("SUMMARY:") and "Adobe\\, CC\\; full" in l for l in lines)


def test_ics_monthly_charges_across_horizon():
    # Weekly custom cycle: horizon of 30 days from May 20 covers Jun 1/8/15
    # (Jun 22 is day 33) -> 3 events.
    events = subscription_events([_sub(1, "Gym", cycle="custom", custom_days=7)],
                                 horizon_days=30, today=D(2024, 5, 20))
    assert [e["date"] for e in events] == [D(2024, 6, 1), D(2024, 6, 8), D(2024, 6, 15)]


def test_ics_trial_end_included():
    sub = _sub(1, "Pro Trial", 20.0, trial=D(2024, 6, 3))
    events = subscription_events([sub], horizon_days=90, today=D(2024, 5, 20))
    # trial end (Jun 3) + monthly charges from Jun 1: 2 events in 90 days
    assert any("TRIAL END" in e["summary"] and e["date"] == D(2024, 6, 3)
               for e in events)
    assert len(events) == 4  # trial end + Jun 1 + Jul 1 + Aug 1


def test_ics_crlf_line_endings():
    data = build_ics(subscription_events([_sub(1, "X")], 30, today=D(2024, 5, 20)))
    assert b"\r\n" in data
    assert b"\n" not in data.replace(b"\r\n", b"")


def test_ics_requires_uid_uniqueness_per_occurrence():
    events = subscription_events([_sub(1, "X", cycle="custom", custom_days=7)],
                                 horizon_days=30, today=D(2024, 5, 20))
    uids = [e["uid"] for e in events]
    assert len(uids) == len(set(uids))
