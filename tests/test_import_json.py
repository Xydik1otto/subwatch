# Імпорт виписок у форматі JSON (поряд із CSV): список об'єктів,
# {"transactions": [...]}, {"statement": {"transactions": [...]}} та
# {"data": [...]}; вкладена сума/валюта (Monzo/Starling-стиль); ті самі
# кандидати повторюваних платежів через спільний detect_recurring.
import json

import pytest
from fastapi.testclient import TestClient

from backend import csvimport, native_accel
from backend.main import app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SUBWATCH_DB", str(tmp_path / "sw.db"))
    return TestClient(app)


def _netflix(n=4, start="2024-01-10", step=30):
    """Чотири місячних списання Netflix з кроком ~30 днів."""
    import datetime as dt
    d0 = dt.date.fromisoformat(start)
    return [
        {"date": (d0 + dt.timedelta(days=step * i)).isoformat(),
         "description": f"NETFLIX.COM {8812 + i}",
         "amount": "15.49", "currency": "USD"}
        for i in range(n)
    ]


# --- parsing -------------------------------------------------------------------

def test_parse_json_bare_list():
    txns = csvimport.parse_json_statement(json.dumps(_netflix()))
    assert len(txns) == 4
    assert txns[0].date.isoformat() == "2024-01-10"
    assert txns[0].description == "NETFLIX.COM 8812"
    assert txns[0].amount == 15.49
    assert txns[0].currency == "USD"


def test_parse_json_wrappers():
    txns = _netflix()
    for wrapper in (lambda rows: rows,
                    lambda rows: {"transactions": rows},
                    lambda rows: {"statement": {"transactions": rows}},
                    lambda rows: {"data": rows}):
        parsed = csvimport.parse_json_statement(json.dumps(wrapper(txns)))
        assert len(parsed) == 4


def test_parse_json_monzo_nested_amount():
    doc = [{"transaction_id": "cz.1",
            "created": "2024-01-10T08:30:00Z",
            "merchant": {"name": "Spotify"},
            "amount": {"value": "9.99", "currency": "EUR"}}] * 3
    doc[1] = dict(doc[1], created="2024-02-10T08:30:00Z")
    doc[2] = dict(doc[2], created="2024-03-10T08:30:00Z")
    txns = csvimport.parse_json_statement(json.dumps(doc))
    assert len(txns) == 3
    assert txns[0].amount == 9.99
    assert txns[0].currency == "EUR"
    assert "Spotify" in txns[0].description
    assert txns[0].date.isoformat() == "2024-01-10"


def test_parse_json_skips_unparsable_rows():
    doc = _netflix() + [{"date": "not-a-date", "amount": "1.00"},
                        {"date": "2024-02-10"},          # без amount
                        {"description": "junk"}]
    txns = csvimport.parse_json_statement(json.dumps(doc))
    assert len(txns) == 4


def test_parse_json_invalid_raises():
    with pytest.raises(ValueError, match="invalid JSON"):
        csvimport.parse_json_statement("{nope")
    with pytest.raises(ValueError, match="no transaction list"):
        csvimport.parse_json_statement('{"balance": 100}')
    with pytest.raises(ValueError, match="no parsable"):
        csvimport.parse_json_statement('[{"description": "only"}]')


def test_parse_statement_routes_csv_and_json():
    csv_text = ("date,description,amount,currency\n"
                "2024-01-10,NETFLIX.COM,15.49,USD\n"
                "2024-02-10,NETFLIX.COM,15.49,USD\n")
    assert len(csvimport.parse_statement(csv_text)) == 2
    assert len(csvimport.parse_statement(json.dumps(_netflix(n=2)))) == 2
    # CSV-синтаксис з preset не «з'їдається» JSON-шляхом
    revolut = ("Completed Date,Description,Amount,Currency\n"
               "2024-01-10,NETFLIX.COM,15.49,USD\n"
               "2024-02-10,NETFLIX.COM,15.49,USD\n")
    assert len(csvimport.parse_statement(revolut, "revolut")) == 2


# --- detection + API ------------------------------------------------------------

def test_json_import_end_to_end_detection():
    payload = json.dumps(_netflix())
    rows, candidates = native_accel.parse_and_detect(payload)
    assert rows == 4
    assert len(candidates) == 1
    c = candidates[0]
    assert c["amount"] == 15.49
    assert c["cycle"] == "monthly"
    assert c["currency"] == "USD"


def test_api_import_analyze_json(client):
    r = client.post("/api/import/analyze",
                    json={"csv": json.dumps(_netflix())})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["parsed_rows"] == 4
    assert len(body["candidates"]) == 1
    cand = body["candidates"][0]
    assert cand["name"].startswith("NETFLIX.COM")
    assert cand["next_due_date"]


def test_api_import_confirm_from_json(client):
    analyze = client.post("/api/import/analyze",
                          json={"csv": json.dumps(_netflix())}).json()
    c = analyze["candidates"][0]
    r = client.post("/api/import/confirm", json={"candidates": [{
        "name": c["name"], "amount": c["amount"], "currency": c["currency"],
        "cycle": c["cycle"], "custom_days": c["custom_days"],
        "next_due_date": c["next_due_date"],
        "description": c["description"]}]})
    assert r.status_code == 200, r.text
    created = r.json()["created"]
    assert len(created) == 1
    assert created[0]["amount"] == 15.49
    assert created[0]["next_due_date"] == c["next_due_date"]


def test_api_import_analyze_invalid_json_422(client):
    r = client.post("/api/import/analyze", json={"csv": "[{oops"})
    assert r.status_code == 422
    assert "invalid JSON" in r.json()["detail"]


def test_csv_import_still_works(client):
    """CSV-шлях не зламаний автодетекцією JSON."""
    csv_text = ("Date,Description,Amount,Currency\n"
                "2024-01-10,NETFLIX.COM 1,15.49,USD\n"
                "2024-02-10,NETFLIX.COM 2,15.49,USD\n"
                "2024-03-10,NETFLIX.COM 3,15.49,USD\n")
    r = client.post("/api/import/analyze", json={"csv": csv_text})
    assert r.status_code == 200, r.text
    assert r.json()["parsed_rows"] == 3
