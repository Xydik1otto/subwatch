# CSV statement import: parsing + recurring-payment detection heuristic.
import datetime as dt

import pytest

from backend.csvimport import Txn, detect_recurring, normalize_description, parse_csv

D = dt.date

MONTHLY_CSV = """Дата;Опис;Сума
01.03.2026;NETFLIX.COM 8812;-16,99
01.04.2026;NETFLIX.COM 4410;-16,99
05.04.2026;COFFEE BAR KYIV;-4,50
01.05.2026;NETFLIX.COM 7734;-16,99
01.06.2026;NETFLIX.COM 2210;-16,99
"""


def test_parse_csv_uk_header_eu_dates_and_amounts():
    txns = parse_csv(MONTHLY_CSV)
    assert len(txns) == 5
    assert txns[0] == Txn(D(2026, 3, 1), "NETFLIX.COM 8812", -16.99)
    assert txns[2] == Txn(D(2026, 4, 5), "COFFEE BAR KYIV", -4.50)


def test_parse_csv_iso_dates_tab_delimiter():
    csv_text = ("date\tdescription\tamount\n"
                "2026-01-05\tSpotify Premium\t9.99\n"
                "2026-02-05\tSpotify Premium\t9.99\n")
    txns = parse_csv(csv_text)
    assert len(txns) == 2
    assert txns[0].date == D(2026, 1, 5)
    assert txns[0].amount == 9.99


def test_parse_csv_no_header_inference():
    csv_text = ("2026-01-10,Acme Cloud,29.00\n"
                "2026-02-10,Acme Cloud,29.00\n"
                "2026-03-10,Acme Cloud,29.00\n")
    txns = parse_csv(csv_text)
    assert [t.amount for t in txns] == [29.00, 29.00, 29.00]
    assert all(t.description == "Acme Cloud" for t in txns)


def test_parse_csv_thousands_and_currency_noise():
    csv_text = ("date,description,amount\n"
                "2026-01-01,Host,\"1 234,56 UAH\"\n"
                "2026-02-01,Host,\"(50.00)\"\n")
    txns = parse_csv(csv_text)
    assert txns[0].amount == 1234.56
    assert txns[1].amount == -50.00  # parentheses = negative


def test_parse_csv_garbage_raises():
    with pytest.raises(ValueError):
        parse_csv("just one line\n")
    with pytest.raises(ValueError):
        parse_csv("date,description,amount\nnot-a-date,x,abc\n")


def test_normalize_description_groups_transaction_ids():
    assert (normalize_description("NETFLIX.COM 8812") ==
            normalize_description("netflix.com  4410!"))
    assert normalize_description("Uber *TRIP 17") != \
        normalize_description("UBER EATS 17")


def test_detect_weekly():
    txns = [Txn(D(2026, 1, 5), "Gym Pass", 10.0),
            Txn(D(2026, 1, 12), "Gym Pass", 10.0),
            Txn(D(2026, 1, 19), "Gym Pass", 10.0),
            Txn(D(2026, 1, 26), "Gym Pass", 10.0)]
    cands = detect_recurring(txns)
    assert len(cands) == 1
    c = cands[0]
    assert c["period_days"] == 7 and c["cycle"] == "custom"
    assert c["custom_days"] == 7
    assert c["next_due_date"] == "2026-02-02"
    assert c["occurrences"] == 4


def test_detect_biweekly_and_yearly():
    biweekly = [Txn(D(2026, 1, 2), "Cleaner", 30.0), Txn(D(2026, 1, 16), "Cleaner", 30.0),
                Txn(D(2026, 1, 30), "Cleaner", 30.0)]
    yearly = [Txn(D(2024, 2, 29), "Domain", 12.0), Txn(D(2025, 2, 28), "Domain", 12.0),
              Txn(D(2026, 2, 28), "Domain", 12.0)]
    cands = {c["name"]: c for c in detect_recurring(biweekly + yearly)}
    assert cands["Cleaner"]["period_days"] == 14
    assert cands["Domain"]["period_days"] == 365 and cands["Domain"]["cycle"] == "yearly"
    # leap-year gap of 365 then 366 days still matches 365 +/-2
    assert cands["Domain"]["next_due_date"] == "2027-02-28"


def test_detect_monthly_with_uneven_calendar_gaps():
    """28/30/31-day month lengths must not break monthly detection."""
    txns = [Txn(D(2024, 1, 1), "Streaming", 9.99), Txn(D(2024, 2, 1), "Streaming", 9.99),
            Txn(D(2024, 3, 1), "Streaming", 9.99), Txn(D(2024, 4, 1), "Streaming", 9.99)]
    cands = detect_recurring(txns)
    assert len(cands) == 1
    assert cands[0]["period_days"] in (30, 31)
    assert cands[0]["cycle"] == "monthly"
    assert cands[0]["next_due_date"] == "2024-05-01"


def test_detect_month_end_anchor_chain():
    """Jan 31 -> Feb 29 -> Mar 31: gaps 29/31 around a 30-day median."""
    txns = [Txn(D(2024, 1, 31), "Storage Box", 5.0),
            Txn(D(2024, 2, 29), "Storage Box", 5.0),
            Txn(D(2024, 3, 31), "Storage Box", 5.0)]
    cands = detect_recurring(txns)
    assert len(cands) == 1
    assert cands[0]["cycle"] == "monthly"
    assert cands[0]["next_due_date"] == "2024-04-30"


def test_detect_rejects_skipped_month():
    txns = [Txn(D(2026, 1, 15), "Idea", 8.0), Txn(D(2026, 2, 15), "Idea", 8.0),
            Txn(D(2026, 4, 15), "Idea", 8.0)]  # 60-day gap: month skipped
    assert detect_recurring(txns) == []


def test_detect_rejects_varying_amounts():
    txns = [Txn(D(2026, 1, 5), "Varies", 10.0), Txn(D(2026, 2, 5), "Varies", 25.0),
            Txn(D(2026, 3, 5), "Varies", 10.0)]
    assert detect_recurring(txns) == []


def test_detect_ignores_fewer_than_three_and_one_offs():
    txns = [Txn(D(2026, 1, 5), "Twice Only", 5.0), Txn(D(2026, 2, 5), "Twice Only", 5.0),
            Txn(D(2026, 3, 1), "One Off", 99.0), Txn(D(2026, 3, 2), "Coffee", 3.0)]
    assert detect_recurring(txns) == []


def test_detect_small_price_change_within_tolerance():
    """A modest price change (+~2%) keeps the group detectable."""
    txns = [Txn(D(2026, 1, 1), "Service", 10.00), Txn(D(2026, 2, 1), "Service", 10.20),
            Txn(D(2026, 3, 1), "Service", 10.20)]
    cands = detect_recurring(txns)
    assert len(cands) == 1 and cands[0]["amount"] == 10.2
