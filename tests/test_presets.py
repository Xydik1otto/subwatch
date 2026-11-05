# CSV bank presets: Revolut / Wise statement column mappings.
import pytest
from fastapi.testclient import TestClient

from backend import csvimport
from backend.main import app

REVOLUT_CSV = (
    "Type,Product,Started Date,Completed Date,Description,Amount,Fee,"
    "Currency,State,Balance\n"
    "CARD_PAYMENT,current,2026-01-02 10:30:44,2026-01-03 08:00:00,"
    "NETFLIX.COM,-15.49,0.00,USD,COMPLETED,1000.00\n"
    "CARD_PAYMENT,current,2026-02-02 10:31:00,2026-02-03 08:00:00,"
    "NETFLIX.COM,-15.49,0.00,USD,COMPLETED,984.51\n"
    "CARD_PAYMENT,current,2026-03-02 10:29:00,2026-03-03 08:00:00,"
    "NETFLIX.COM,-15.49,0.00,USD,COMPLETED,969.02\n"
    "TOPUP,current,2026-03-05 09:00:00,2026-03-05 09:00:01,"
    "Top-up,-50.00,0.00,USD,COMPLETED,1019.02\n"
)

WISE_CSV = (
    "TransferWise ID,Date,Amount,Currency,Description,Payment Reference,"
    "Running Balance\n"
    "CARD-123,02-01-2026,-9.99,EUR,SPOTIFY AB,sub,500.01\n"
    "CARD-124,02-02-2026,-9.99,EUR,SPOTIFY AB,sub,490.02\n"
    "CARD-125,02-03-2026,-9.99,EUR,SPOTIFY AB,sub,480.03\n"
)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SUBWATCH_DB", str(tmp_path / "sw.db"))
    return TestClient(app)


def _analyze(client, csv_text, preset):
    return client.post("/api/import/analyze",
                       json={"csv": csv_text, "preset": preset})


def test_presets_endpoint_lists_revolut_and_wise(client):
    data = client.get("/api/import/presets").json()
    ids = {p["id"] for p in data}
    assert {"revolut", "wise"} <= ids
    for p in data:
        assert p["label"] and p["columns"]["date"] and p["columns"]["amount"]


def test_revolut_preset_maps_columns_and_currency(client):
    r = _analyze(client, REVOLUT_CSV, "revolut")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["parsed_rows"] == 4
    cand = next(c for c in body["candidates"]
                if "NETFLIX" in c["name"].upper())
    assert cand["amount"] == 15.49
    assert cand["currency"] == "USD"
    assert cand["cycle"] == "monthly"
    # next due = one month after the last charge (2026-03-02, anchor day 2)
    assert cand["next_due_date"] == "2026-04-02"


def test_wise_preset_reads_dayfirst_dates_and_currency(client):
    r = _analyze(client, WISE_CSV, "wise")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["parsed_rows"] == 3
    cand = body["candidates"][0]
    assert cand["amount"] == 9.99
    assert cand["currency"] == "EUR"
    assert cand["cycle"] == "monthly"
    # 02-03-2026 is day-first: March 2nd, not February 3rd
    assert cand["next_due_date"] == "2026-04-02"


def test_unknown_preset_422(client):
    r = _analyze(client, REVOLUT_CSV, "monobank")
    assert r.status_code == 422
    assert "unknown preset" in r.json()["detail"]


def test_preset_with_mismatched_header_422(client):
    r = _analyze(client, "foo,bar\n1,2\n3,4\n", "revolut")
    assert r.status_code == 422


def test_revolut_timestamp_dates_parse():
    txns = csvimport.parse_csv(REVOLUT_CSV, "revolut")
    assert all(t.date.isoformat().count("-") == 2 for t in txns)
    assert txns[0].date.year == 2026


def test_generic_autodetect_still_works_without_preset():
    txns = csvimport.parse_csv(
        "date,description,amount\n2026-01-01,NETFLIX,15.49\n"
        "2026-02-01,NETFLIX,15.49\n2026-03-01,NETFLIX,15.49\n")
    assert len(txns) == 3
    assert all(t.currency == "USD" for t in txns)
