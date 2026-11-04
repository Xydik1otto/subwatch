# RFC 5545 ICS calendar export of upcoming subscription charges.
from __future__ import annotations

import datetime as dt


def _dt_date(d: dt.date) -> str:
    return d.strftime("%Y%m%d")


def _escape(text: str) -> str:
    return (text.replace("\\", "\\\\").replace(";", "\\;")
                .replace(",", "\\,").replace("\n", "\\n"))


def build_ics(events: list[dict], cal_name: str = "Subwatch") -> bytes:
    """events: [{uid, date, summary, description}] -> ICS bytes (CRLF lines)."""
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//subwatch//local//EN",
        "CALSCALE:GREGORIAN",
        f"X-WR-CALNAME:{_escape(cal_name)}",
    ]
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for ev in events:
        lines += [
            "BEGIN:VEVENT",
            f"UID:{_escape(ev['uid'])}",
            f"DTSTAMP:{stamp}",
            f"DTSTART;VALUE=DATE:{_dt_date(ev['date'])}",
            f"DTEND;VALUE=DATE:{_dt_date(ev['date'] + dt.timedelta(days=1))}",
            f"SUMMARY:{_escape(ev['summary'])}",
            f"DESCRIPTION:{_escape(ev['description'])}",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return ("\r\n".join(lines) + "\r\n").encode("utf-8")


def subscription_events(subs: list, horizon_days: int = 90,
                        today: dt.date | None = None) -> list[dict]:
    """Turn subscription rows into ICS events for every charge in the horizon."""
    from . import schedule

    today = today or dt.date.today()
    events = []
    for s in subs:
        start = dt.date.fromisoformat(s["next_due_date"])
        trial_end = dt.date.fromisoformat(s["trial_end_date"]) if s["trial_end_date"] else None
        dates = []
        if trial_end and today <= trial_end <= today + dt.timedelta(days=horizon_days):
            dates.append(trial_end)
        anchor = s["anchor_day"] if "anchor_day" in s.keys() else None
        dates += schedule.upcoming_dates(start, s["cycle"],
                                         s["custom_days"], horizon_days, today,
                                         anchor)
        for i, d in enumerate(dates):
            label = "TRIAL END" if (trial_end and d == trial_end) else "Charge"
            events.append({
                "uid": f"subwatch-{s['id']}-{d.isoformat()}-{i}@local",
                "date": d,
                "summary": f"{label}: {s['name']} "
                           f"({s['amount']:.2f} {s['currency']})",
                "description": f"{s['name']} — {s['cycle']} "
                               f"({'every ' + str(s['custom_days']) + ' days' if s['cycle'] == 'custom' else 'renews'}) "
                               f"at {s['amount']:.2f} {s['currency']}",
            })
    return events
