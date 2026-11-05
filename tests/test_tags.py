# Tag analytics: monthly spend per tag + SVG pie chart.
import math
import re

import pytest
from fastapi.testclient import TestClient

from backend import tags
from backend.main import app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SUBWATCH_DB", str(tmp_path / "sw.db"))
    return TestClient(app)


def _mk(client, name, amount, tags_s, cycle="monthly",
        next_due="2026-12-01", currency="USD", **extra):
    body = {"name": name, "amount": amount, "currency": currency,
            "cycle": cycle, "next_due_date": next_due, "tags": tags_s}
    body.update(extra)
    r = client.post("/api/subscriptions", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_parse_tags_normalizes_and_dedupes():
    assert tags.parse_tags("Video, MUSIC ,video") == ["video", "music"]
    assert tags.parse_tags(None) == []
    assert tags.parse_tags(" , ") == []


def test_monthly_by_tag_groups_and_skips_paused():
    rows = [
        {"amount": 10.0, "cycle": "monthly", "custom_days": None,
         "currency": "USD", "tags": "video", "paused": 0},
        {"amount": 120.0, "cycle": "yearly", "custom_days": None,
         "currency": "USD", "tags": "video, music", "paused": 0},
        {"amount": 5.0, "cycle": "monthly", "custom_days": None,
         "currency": "USD", "tags": None, "paused": 1},   # paused → skipped
    ]
    out = {t["tag"]: t["monthly_by_currency"] for t in tags.monthly_by_tag(rows)}
    assert out["video"]["USD"] == pytest.approx(10.0 + 10.0)
    assert out["music"]["USD"] == pytest.approx(10.0)
    assert "" not in out   # paused untagged sub is skipped entirely


def test_monthly_by_tag_untagged_bucket():
    rows = [{"amount": 7.5, "cycle": "monthly", "custom_days": None,
             "currency": "EUR", "tags": "", "paused": 0}]
    out = tags.monthly_by_tag(rows)
    assert out == [{"tag": "", "monthly_by_currency": {"EUR": 7.5}}]


def test_api_tags_endpoint(client):
    _mk(client, "Netflix", 15.0, "video")
    _mk(client, "Spotify", 10.0, "music, audio")
    _mk(client, "Gym", 30.0, None)
    data = client.get("/api/tags").json()
    by_tag = {t["tag"]: t["monthly_by_currency"] for t in data["tags"]}
    assert by_tag["video"] == {"USD": 15.0}
    assert by_tag["music"] == {"USD": 10.0}
    assert by_tag["audio"] == {"USD": 10.0}
    assert by_tag["(без тегу)"] == {"USD": 30.0}
    assert data["primary_currency"] == "USD"


def test_api_tags_svg_pie(client):
    _mk(client, "Netflix", 15.0, "video")
    _mk(client, "Spotify", 10.0, "music")
    r = client.get("/api/tags.svg")
    assert r.status_code == 200
    assert "image/svg" in r.headers["content-type"]
    svg = r.text
    assert "<svg" in svg and 'aria-label="Витрати по тегах' in svg
    # two slices -> two <path> elements
    assert len(re.findall(r"<path ", svg)) == 2
    assert "video — 15.00 USD" in svg
    assert "(60.0%)" in svg and "(40.0%)" in svg


def test_svg_slice_geometry_sums_to_full_circle():
    breakdown = [{"tag": "a", "monthly_by_currency": {"USD": 3.0}},
                 {"tag": "b", "monthly_by_currency": {"USD": 1.0}}]
    svg = tags.build_svg(breakdown, "USD")
    # a 75/25 split: the big slice must use the large-arc flag
    assert 'A 100.00 100.00 0 1 1' in svg or "A 100.00 100.00 0 1" in svg
    assert "a — 3.00 USD (75.0%)" in svg
    assert "b — 1.00 USD (25.0%)" in svg


def test_svg_empty_state():
    svg = tags.build_svg([], "USD")
    assert "немає даних" in svg
