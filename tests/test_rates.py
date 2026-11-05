# Multi-currency summary via ECB reference rates: parsing, caching,
# offline fallback, cross-rate conversion, API wiring.
import pytest
from fastapi.testclient import TestClient

from backend import rates
from backend.main import app

SAMPLE_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<gesmes:Envelope xmlns:gesmes="http://www.gesmes.org/xml/2002-08-01"
                 xmlns="http://www.ecb.int/vocabulary/2002-08-01/eurofxref">
  <Cube>
    <Cube time="2026-11-04">
      <Cube currency="USD" rate="1.1"/>
      <Cube currency="PLN" rate="4.3"/>
      <Cube currency="UAH" rate="45.5"/>
    </Cube>
  </Cube>
</gesmes:Envelope>"""


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SUBWATCH_DB", str(tmp_path / "sw.db"))
    monkeypatch.setenv("SUBWATCH_RATES_CACHE", str(tmp_path / "rates.json"))
    return TestClient(app)


def test_parse_ecb_xml_namespace_agnostic():
    r = rates.parse_ecb_xml(SAMPLE_XML)
    assert r["EUR"] == 1.0
    assert r["USD"] == 1.1 and r["PLN"] == 4.3 and r["UAH"] == 45.5


def test_parse_ecb_xml_empty_raises():
    with pytest.raises(ValueError):
        rates.parse_ecb_xml(b"<Envelope><Cube/></Envelope>")


def test_get_rates_writes_cache_on_success(tmp_path, monkeypatch):
    cache = str(tmp_path / "rates.json")
    monkeypatch.setattr(rates, "fetch_rates", lambda *a, **k: dict(rates_EUR))
    assert rates.get_rates(cache=cache) == rates_EUR
    # second call with a failing fetcher still returns the cached set
    def boom(*a, **k):
        raise OSError("offline")
    assert rates.get_rates(fetcher=boom, cache=cache) == rates_EUR


rates_EUR = {"EUR": 1.0, "USD": 1.1, "PLN": 4.3}


def test_get_rates_offline_without_cache_returns_empty(tmp_path):
    def boom(*a, **k):
        raise OSError("offline")
    assert rates.get_rates(fetcher=boom, cache=str(tmp_path / "none.json")) == {}


def test_convert_cross_rate_through_eur():
    fx = {"EUR": 1.0, "USD": 1.1, "PLN": 4.3}
    assert rates.convert(110.0, "USD", "EUR", fx) == pytest.approx(100.0)
    assert rates.convert(43.0, "PLN", "USD", fx) == pytest.approx(43 / 4.3 * 1.1)
    assert rates.convert(5.0, "USD", "USD", fx) == 5.0
    assert rates.convert(5.0, "USD", "GBP", fx) is None
    assert rates.convert(5.0, "USD", "EUR", {}) is None


def test_summary_base_conversion(client, monkeypatch):
    monkeypatch.setattr(rates, "get_rates",
                        lambda *a, **k: {"EUR": 1.0, "USD": 1.1, "PLN": 4.3})
    client.post("/api/subscriptions", json={
        "name": "A", "amount": 10.0, "currency": "USD", "cycle": "monthly",
        "next_due_date": "2026-06-01"})
    client.post("/api/subscriptions", json={
        "name": "B", "amount": 43.0, "currency": "PLN", "cycle": "monthly",
        "next_due_date": "2026-06-01"})
    s = client.get("/api/summary", params={"base": "USD"}).json()
    assert s["base"] == "USD"
    # 10 USD + 43 PLN (== 10 EUR == 11 USD) = 21 USD/month
    assert s["monthly_in_base"] == pytest.approx(21.0, abs=0.01)
    assert s["yearly_in_base"] == pytest.approx(252.0, abs=0.1)
    # per-currency totals are untouched
    assert s["monthly_by_currency"]["PLN"] == 43.0


def test_summary_base_offline_no_cache_503(client, monkeypatch):
    monkeypatch.setattr(rates, "get_rates", lambda *a, **k: {})
    r = client.get("/api/summary", params={"base": "USD"})
    assert r.status_code == 503


def test_summary_base_unknown_currency_503(client, monkeypatch):
    monkeypatch.setattr(rates, "get_rates",
                        lambda *a, **k: {"EUR": 1.0, "USD": 1.1})
    client.post("/api/subscriptions", json={
        "name": "X", "amount": 5.0, "currency": "XYZ", "cycle": "monthly",
        "next_due_date": "2026-06-01"})
    r = client.get("/api/summary", params={"base": "USD"})
    assert r.status_code == 503
    assert "XYZ" in r.json()["detail"]


def test_summary_without_base_unchanged_shape(client):
    client.post("/api/subscriptions", json={
        "name": "A", "amount": 10.0, "cycle": "monthly",
        "next_due_date": "2026-06-01"})
    s = client.get("/api/summary").json()
    assert "base" not in s and "monthly_in_base" not in s
    assert s["monthly_by_currency"]["USD"] == 10.0
