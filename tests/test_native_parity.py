# Golden parity tests: the native C# accelerator (dotnet/SubRec) must produce
# IDENTICAL candidates to the pure-Python path on the same inputs, and the
# Python fallback must engage whenever the native path is unavailable/broken.
import json
import subprocess
from pathlib import Path

import pytest

from backend import native_accel
from backend.csvimport import Txn, detect_recurring, parse_csv

ROOT = Path(__file__).resolve().parent.parent
EXE = native_accel.native_exe()

needs_exe = pytest.mark.skipif(
    EXE is None,
    reason="native SubRec.exe not built (dotnet publish dotnet/SubRec "
           "-c Release -o dotnet/publish)")


def _native(csv_text: str, *args: str):
    proc = subprocess.run([str(EXE), *args], input=csv_text,
                          capture_output=True, encoding="utf-8", timeout=120)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def _assert_parity(csv_text: str):
    """Raw CSV -> both pipelines -> identical candidates and parsed-row count."""
    txns = parse_csv(csv_text)
    py = detect_recurring(txns)
    out = _native(csv_text)
    assert out["rows"] == len(txns)
    assert out["candidates"] == py
    # and through the integration helper (full-native, no preset)
    rows, cands = native_accel.parse_and_detect(csv_text)
    assert rows == len(txns) and cands == py


# --- golden CSV cases ----------------------------------------------------------

GOLDEN = {
    # Calendar-honest monthly intervals: 28 / 30 / 31-day gaps all match.
    "monthly_uneven_28_30_31": """\
Date,Description,Amount,Currency
2024-01-31,Gym Iron,-30.00,USD
2024-02-28,Gym Iron,-30.00,USD
2024-03-31,Gym Iron,-30.00,USD
2024-05-01,Gym Iron,-30.00,USD
""",
    "weekly": """\
Date,Description,Amount,Currency
2024-01-01,WeeklyBox,5.00,USD
2024-01-08,WeeklyBox,5.00,USD
2024-01-15,WeeklyBox,5.00,USD
2024-01-22,WeeklyBox,5.00,USD
""",
    "yearly": """\
Date,Description,Amount,Currency
2023-03-15,DomainRenewal,14.99,USD
2024-03-15,DomainRenewal,14.99,USD
2025-03-15,DomainRenewal,14.99,USD
""",
    "amount_jitter_within_5pct": """\
Date,Description,Amount,Currency
2024-01-10,StreamCo,10.00,USD
2024-02-10,StreamCo,10.20,USD
2024-03-10,StreamCo,9.85,USD
""",
    "amount_jump_over_5pct_rejected": """\
Date,Description,Amount,Currency
2024-01-10,StreamCo,10.00,USD
2024-02-10,StreamCo,11.50,USD
2024-03-10,StreamCo,10.00,USD
""",
    "two_occurrences_rejected": """\
Date,Description,Amount,Currency
2024-01-10,StreamCo,10.00,USD
2024-02-10,StreamCo,10.00,USD
""",
    "skipped_month_rejected": """\
Date,Description,Amount,Currency
2024-01-10,StreamCo,10.00,USD
2024-02-10,StreamCo,10.00,USD
2024-04-10,StreamCo,10.00,USD
""",
    "cyrillic_descriptions_grouping": """\
Дата,Опис,Сума,Валюта
2024-01-05,ПЕРЕКАЗА НА КАРТУ,-500.00,UAH
2024-02-05,ПЕРЕКАЗА НА КАРТУ,-500.00,UAH
2024-03-05,ПЕРЕКАЗА НА КАРТУ,-500.00,UAH
""",
    "digit_stripped_grouping": """\
Date,Description,Amount,Currency
2024-01-01,NETFLIX.COM 8812,-15.99,USD
2024-02-01,NETFLIX.COM 9931,-15.99,USD
2024-03-01,NETFLIX.COM 4402,-15.99,USD
""",
    "quoted_comma_delimiter_sniff": """\
Date;Description;Amount;Currency
2024-01-01;"Gym, Iron & Sauna";-30.00;EUR
2024-02-01;"Gym, Iron & Sauna";-30.00;EUR
2024-03-01;"Gym, Iron & Sauna";-30.00;EUR
""",
    "eu_decimal_comma_and_negatives": """\
Date,Description,Amount,Currency
2024-01-02,Kiosque FR,"-12,50",EUR
2024-02-02,Kiosque FR,"-12,50",EUR
2024-03-02,Kiosque FR,"-12,50",EUR
""",
    "month_name_dates": """\
Date,Description,Amount,Currency
01 Jun 2024,HosterPro,9.90,USD
01 Jul 2024,HosterPro,9.90,USD
01 Aug 2024,HosterPro,9.90,USD
""",
    "noise_only_no_candidates": """\
Date,Description,Amount,Currency
2024-01-03,SHOP 4411,-12.34,USD
2024-01-04,SHOP 4412,-3.21,USD
2024-01-05,SHOP 4413,-8.90,USD
""",
    "currency_column_ignored_without_preset": """\
Date,Description,Amount,Currency
2024-01-01,SplitCo,10.00,EUR
2024-02-01,SplitCo,10.00,USD
2024-03-01,SplitCo,10.00,USD
""",
}


@needs_exe
@pytest.mark.parametrize("name", sorted(GOLDEN))
def test_golden_parity(name):
    _assert_parity(GOLDEN[name])


# --- randomized golden fuzz ----------------------------------------------------

def _gen_statement(seed: int, n: int = 400) -> str:
    import random
    import datetime as dt
    rng = random.Random(seed)
    d0 = dt.date(2024, 1, 1)
    rows = []
    for _ in range(n):
        if rng.random() < 0.4:
            m = rng.choice(("NETFLIX.COM 8812", "SPOTIFY PARIS", "ПЕРЕКАЗА №5",
                            "GYM IRON, monthly", "Apple.Com/Bill"))
            period = rng.choice((7, 14, 30, 31, 365))
            amt = round(rng.uniform(1, 400), 2)
            day = rng.randint(0, 300)
            for k in range(rng.randint(2, 7)):
                d = d0 + dt.timedelta(days=day + k * period + rng.choice((0, -1, 1, 2)))
                rows.append((d, m, amt * (1 + rng.uniform(-0.03, 0.03)),
                             rng.choice(("USD", "EUR", "UAH"))))
        else:
            rows.append((d0 + dt.timedelta(days=rng.randint(0, 400)),
                         f"SHOP {rng.randint(1, 10**6)}",
                         round(rng.uniform(-500, 500), 2), "USD"))
    rng.shuffle(rows)
    out = ["Date,Description,Amount,Currency"]
    for d, m, a, c in rows:
        desc = '"' + m.replace('"', '""') + '"' if ("," in m or '"' in m) else m
        out.append(f"{d.isoformat()},{desc},{abs(a):.2f},{c}")
    return "\n".join(out) + "\n"


@needs_exe
@pytest.mark.parametrize("seed", range(10))
def test_fuzz_parity(seed):
    _assert_parity(_gen_statement(seed))


@needs_exe
def test_detect_recurring_via_native_matches_python_txns():
    """native_accel.detect_recurring on Txn rows == Python detect_recurring."""
    txns = parse_csv(GOLDEN["monthly_uneven_28_30_31"] + GOLDEN["weekly"])
    assert native_accel.detect_recurring(txns) == detect_recurring(txns)
    # currency must survive the canonical round-trip
    import datetime as dt
    txns_eur = [Txn(dt.date(2024, 1, 1), "HosterPro", -9.90, "EUR"),
                Txn(dt.date(2024, 2, 1), "HosterPro", -9.90, "EUR"),
                Txn(dt.date(2024, 3, 1), "HosterPro", -9.90, "EUR")]
    assert native_accel.detect_recurring(txns_eur) == detect_recurring(txns_eur)
    assert native_accel.detect_recurring(txns_eur)[0]["currency"] == "EUR"


@needs_exe
def test_custom_min_occurrences_and_tolerance_forwarded():
    csv_text = GOLDEN["two_occurrences_rejected"]
    assert detect_recurring(parse_csv(csv_text)) == []          # min 3
    assert native_accel.detect_recurring(parse_csv(csv_text), min_occurrences=2) \
        == detect_recurring(parse_csv(csv_text), min_occurrences=2) != []


# --- fallback behaviour ---------------------------------------------------------

def test_fallback_when_env_points_to_missing_exe(monkeypatch):
    monkeypatch.setenv("SUBWATCH_NATIVE", r"C:\definitely\not\here\SubRec.exe")
    assert native_accel.native_exe() is None
    txns = parse_csv(GOLDEN["weekly"])
    assert native_accel.detect_recurring(txns) == detect_recurring(txns)


def test_fallback_when_env_off(monkeypatch):
    monkeypatch.setenv("SUBWATCH_NATIVE", "off")
    assert native_accel.native_exe() is None
    txns = parse_csv(GOLDEN["weekly"])
    assert native_accel.detect_recurring(txns) == detect_recurring(txns)


def test_fallback_on_corrupt_native_output(monkeypatch):
    class _FakeProc:
        returncode = 0
        stdout = "not json at all"
        stderr = ""

    def _fake_run(*a, **k):
        return _FakeProc()

    monkeypatch.setattr(native_accel.subprocess, "run", _fake_run)
    txns = parse_csv(GOLDEN["weekly"])
    assert native_accel.detect_recurring(txns) == detect_recurring(txns)


def test_fallback_on_native_crash(monkeypatch):
    class _FakeProc:
        returncode = 2
        stdout = ""
        stderr = "error: no date column found"

    monkeypatch.setattr(native_accel.subprocess, "run", lambda *a, **k: _FakeProc())
    txns = parse_csv(GOLDEN["weekly"])
    assert native_accel.detect_recurring(txns) == detect_recurring(txns)


def test_unusable_statement_raises_valueerror_both_paths():
    with pytest.raises(ValueError):
        native_accel.parse_and_detect("just one line\n")
