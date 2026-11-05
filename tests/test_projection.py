# Annual projection: per-month charge buckets + SVG chart.
import datetime as dt
import re

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.projection import bucket_labels, build_svg, monthly_projection

D = dt.date


def _sub(i, name, amount, ccy="USD", cycle="monthly", custom_days=None,
         due=D(2027, 1, 15), paused=False, anchor=None):
    return {"id": i, "name": name, "amount": amount, "currency": ccy,
            "cycle": cycle, "custom_days": custom_days,
            "anchor_day": anchor, "next_due_date": due.isoformat(),
            "trial_end_date": None, "notes": None, "tags": None,
            "active": 1, "paused": paused}


def test_bucket_labels_wrap_year():
    assert bucket_labels(D(2026, 11, 5), 3) == ["2026-11", "2026-12", "2027-01"]
    assert bucket_labels(D(2026, 12, 5), 2) == ["2026-12", "2027-01"]


def test_projection_monthly_charge_in_each_bucket():
    rows = [_sub(1, "A", 10.0, due=D(2026, 12, 15))]
    proj = monthly_projection(rows, today=D(2026, 11, 20), months=12)
    assert [b["month"] for b in proj][0] == "2026-11"
    # Dec 15, Jan 15, ... charges: first bucket empty, then 10 USD each month
    assert proj[0]["totals"] == {}
    assert all(b["totals"].get("USD") == 10.0 for b in proj[1:5])


def test_projection_month_end_anchor_charge_lands_in_right_month():
    # Dec 31 anchored charge: Dec bucket, then Jan 31, Feb 28 (clamped)...
    rows = [_sub(1, "EOM", 5.0, due=D(2026, 12, 31), anchor=31)]
    proj = monthly_projection(rows, today=D(2026, 12, 1), months=3)
    assert proj[0]["totals"] == {"USD": 5.0}   # Dec 31
    assert proj[1]["totals"] == {"USD": 5.0}   # Jan 31
    assert proj[2]["totals"] == {"USD": 5.0}   # Feb 28


def test_projection_yearly_charge_in_single_month():
    rows = [_sub(1, "Domain", 120.0, cycle="yearly", due=D(2027, 3, 1))]
    proj = monthly_projection(rows, today=D(2026, 11, 1), months=12)
    charged = [b for b in proj if b["totals"]]
    assert len(charged) == 1
    assert charged[0]["month"] == "2027-03"
    assert charged[0]["totals"] == {"USD": 120.0}


def test_projection_paused_excluded():
    rows = [_sub(1, "Frozen", 100.0, paused=True),
            _sub(2, "Live", 10.0)]
    proj = monthly_projection(rows, today=D(2026, 11, 1), months=12)
    # Nov and Dec are empty (due Jan 15); every charged month = 10 USD only
    assert proj[0]["totals"] == {} and proj[1]["totals"] == {}
    assert all(b["totals"] == {"USD": 10.0} for b in proj[2:])


def test_projection_multi_currency_separated():
    rows = [_sub(1, "USD sub", 10.0), _sub(2, "EUR sub", 7.0, ccy="EUR")]
    proj = monthly_projection(rows, today=D(2026, 11, 1), months=12)
    assert proj[2]["totals"] == {"USD": 10.0, "EUR": 7.0}


def test_projection_charges_beyond_horizon_cut_off():
    # weekly sub: 12-month horizon starting Nov 1 2026 ends Oct 31 2027;
    # a charge on Nov 2 2027 (index 12) must NOT leak into the chart
    rows = [_sub(1, "W", 7.0, cycle="custom", custom_days=7,
                 due=D(2027, 11, 2))]
    proj = monthly_projection(rows, today=D(2026, 11, 1), months=12)
    assert all(not b["totals"] for b in proj)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SUBWATCH_DB", str(tmp_path / "sw.db"))
    return TestClient(app)


def test_projection_endpoint_today_override(client):
    client.post("/api/subscriptions", json={
        "name": "A", "amount": 10.0, "cycle": "monthly",
        "next_due_date": "2027-01-15"})
    data = client.get("/api/projection",
                      params={"today": "2026-11-01"}).json()
    assert data["primary_currency"] == "USD"
    assert len(data["months"]) == 12
    assert data["months"][0]["month"] == "2026-11"
    assert data["months"][2]["month"] == "2027-01"
    assert data["months"][2]["totals"]["USD"] == 10.0


def test_projection_endpoint_months_validation(client):
    assert client.get("/api/projection", params={"months": 0}).status_code == 422
    assert client.get("/api/projection", params={"months": 37}).status_code == 422


def test_projection_svg_endpoint(client):
    client.post("/api/subscriptions", json={
        "name": "A", "amount": 10.0, "cycle": "monthly",
        "next_due_date": "2027-01-15"})
    r = client.get("/api/projection.svg")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/svg+xml")
    svg = r.content.decode("utf-8")
    assert svg.startswith('<svg xmlns="http://www.w3.org/2000/svg"')
    assert svg.count("<rect") == 12          # one bar per month
    assert "Projection: 12 months (USD)" in svg
    assert ">27-01</text>" in svg            # short month labels
    assert re.search(r">10</text>", svg)     # value labels present


def test_build_svg_empty_data_renders_zero_scale():
    proj = [{"month": "2026-11", "totals": {}},
            {"month": "2026-12", "totals": {}}]
    svg = build_svg(proj, "USD")
    assert svg.count("<rect") == 2
    assert 'height="0.0"' in svg
