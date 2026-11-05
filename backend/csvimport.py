# CSV statement import + recurring-payment detection heuristics.
#
# Pipeline: raw CSV text -> parse_csv() -> list[Txn] (date, description,
# amount) -> detect_recurring() -> candidates for the user to confirm.
#
# The heuristic groups transactions by a normalized description (digits and
# punctuation stripped, so "NETFLIX.COM 8812" and "NETFLIX.COM 9931" group
# together), then checks that consecutive-transaction gaps are all within
# +/-2 days of one known period (7 / 14 / 30 / 31 / 365) and the amounts are
# near-identical. Calendar-honest intervals (28/30/31 for a monthly charge)
# therefore still match, but a skipped month (a 60-day gap) breaks the group.
from __future__ import annotations

import csv
import datetime as dt
import io
import re
import statistics
from dataclasses import dataclass

KNOWN_PERIODS = (7, 14, 30, 31, 365)
DATE_TOLERANCE = 2          # days a real-world gap may deviate from the period
AMOUNT_TOLERANCE = 0.05     # relative spread allowed inside one group
MIN_OCCURRENCES = 3

_MONTH_NAMES = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


@dataclass(frozen=True)
class Txn:
    date: dt.date
    description: str
    amount: float
    currency: str = "USD"


# --- bank presets -------------------------------------------------------------
# Column mappings for well-known bank statement exports. Each preset maps the
# canonical fields (date/description/amount/currency) to a list of possible
# header names (matched case-insensitively, exact match preferred).

PRESETS: dict[str, dict] = {
    "revolut": {
        "label": "Revolut (statement CSV)",
        "columns": {
            "date": ["completed date", "started date"],
            "description": ["description"],
            "amount": ["amount"],
            "currency": ["currency"],
        },
    },
    "wise": {
        "label": "Wise / TransferWise (statement CSV)",
        "columns": {
            "date": ["date"],
            "description": ["description"],
            "amount": ["amount"],
            "currency": ["currency"],
        },
    },
}


# --- parsing -----------------------------------------------------------------

_DATE_FORMATS = (
    "%Y-%m-%d",   # 2024-06-01
    "%d.%m.%Y",   # 01.06.2024
    "%d/%m/%Y",   # 01/06/2024 (day-first wins ties, EU statements)
    "%m/%d/%Y",   # 06/01/2024
    "%d-%m-%Y",   # 01-06-2024
    "%Y.%m.%d",   # 2024.06.01
    "%Y/%m/%d",
)


def _parse_date(value: str) -> dt.date | None:
    v = value.strip().strip('"').strip("'")
    # Timestamps ('2024-06-01 10:30:44', '2024-06-01T10:30'): keep the date part.
    m = re.match(r"^(\d{4}-\d{2}-\d{2})[ T]", v)
    if m:
        v = m.group(1)
    for fmt in _DATE_FORMATS:
        try:
            return dt.datetime.strptime(v, fmt).date()
        except ValueError:
            continue
    m = re.match(r"^(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})$", v)      # 01 Jun 2024
    if m and m.group(2).lower()[:3] in _MONTH_NAMES:
        return dt.date(int(m.group(3)), _MONTH_NAMES[m.group(2).lower()[:3]],
                       int(m.group(1)))
    m = re.match(r"^([A-Za-z]{3})\s+(\d{1,2}),?\s+(\d{4})$", v)    # Jun 1, 2024
    if m and m.group(1).lower()[:3] in _MONTH_NAMES:
        return dt.date(int(m.group(3)), _MONTH_NAMES[m.group(1).lower()[:3]],
                       int(m.group(2)))
    return None


_CURRENCY_NOISE = re.compile(r"(?i)(uah|usd|eur|грн|₴|\$|€|£)")


def _parse_amount(raw: str) -> float | None:
    s = raw.strip().strip('"').strip("'")
    neg = bool(re.search(r"^-|-\s*$|^\(.*\)$", s))
    s = _CURRENCY_NOISE.sub("", s)
    s = s.replace("\u00a0", "").replace(" ", "").strip("()+-")
    if not re.fullmatch(r"[\d.,]+", s):
        return None
    if "," in s and "." in s:
        # The right-most separator is the decimal one; the other is thousands.
        dec = "," if s.rfind(",") > s.rfind(".") else "."
        s = s.replace("," if dec == "." else ".", "")
        s = s.replace(dec, ".")
    elif "," in s:
        s = s.replace(",", ".")   # EU decimal comma: "1234,56"
    try:
        value = float(s)
    except ValueError:
        return None
    return -value if neg else value


def _sniff_delimiter(sample_line: str) -> str:
    counts = {d: sample_line.count(d) for d in (",", ";", "\t", "|")}
    best = max(counts, key=lambda d: counts[d])
    return best if counts[best] > 0 else ","


_DATE_HINTS = ("date", "дата")
_DESC_HINTS = ("description", "опис", "призначен", "detail", "merchant",
               "payee", "найменув")
_AMT_HINTS = ("amount", "сума", "sum", "value", "debit", "credit")


def _looks_like_header(cells: list[str]) -> bool:
    joined = "|".join(c.strip().lower() for c in cells)
    hits = sum(any(h in joined for h in hints)
               for hints in (_DATE_HINTS, _DESC_HINTS, _AMT_HINTS))
    return hits >= 2


def _column_scores(rows: list[list[str]]):
    """Score each column: how many values parse as a date / a number."""
    n = max(len(r) for r in rows)
    date_hits = [0] * n
    num_hits = [0] * n
    for row in rows:
        for i, cell in enumerate(row):
            if _parse_date(cell):
                date_hits[i] += 1
            if _parse_amount(cell) is not None:
                num_hits[i] += 1
    return date_hits, num_hits


def _preset_columns(header: list[str], columns: dict[str, list[str]]) -> dict[str, int]:
    """Match preset alias lists against the header row -> column indexes."""
    lowered = [c.strip().lower() for c in header]
    out: dict[str, int] = {}
    for field, aliases in columns.items():
        idx = next((i for i, h in enumerate(lowered) if h in aliases), None)
        if idx is None:   # fallback: substring match
            idx = next((i for i, h in enumerate(lowered)
                        if any(a in h for a in aliases)), None)
        if idx is not None:
            out[field] = idx
    return out


def parse_csv(text: str, preset_name: str | None = None) -> list[Txn]:
    """Parse a bank/CSV statement into (date, description, amount) rows.

    Auto-detects the delimiter, an optional header row, the date format and
    the amount format (EU decimal commas, currency symbols, negatives).
    With `preset_name` (see PRESETS — 'revolut', 'wise') the header row is
    matched against the bank's known column names instead of guessing.
    Raises ValueError when the file does not contain a usable statement.
    """
    text = text.lstrip("﻿")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if len(lines) < 2:
        raise ValueError("CSV needs at least 2 non-empty lines")
    delim = _sniff_delimiter(lines[0])
    rows = [next(csv.reader([ln], delimiter=delim)) for ln in lines]

    col_date = col_desc = col_amt = col_ccy = None
    start = 0
    if preset_name:
        if preset_name not in PRESETS:
            raise ValueError(f"unknown preset: {preset_name}")
        cols = _preset_columns(rows[0], PRESETS[preset_name]["columns"])
        if "date" not in cols or "amount" not in cols:
            raise ValueError(
                f"preset '{preset_name}': no matching date/amount columns "
                "in the header row")
        col_date, col_amt = cols["date"], cols["amount"]
        col_desc = cols.get("description")
        col_ccy = cols.get("currency")
        start = 1
    elif _looks_like_header(rows[0]):
        header = [c.strip().lower() for c in rows[0]]
        for i, h in enumerate(header):
            if col_date is None and any(k in h for k in _DATE_HINTS):
                col_date = i
            elif col_desc is None and any(k in h for k in _DESC_HINTS):
                col_desc = i
            elif col_amt is None and any(k in h for k in _AMT_HINTS):
                col_amt = i
        start = 1
    if col_date is None or col_amt is None:
        body = rows[start:]
        date_hits, num_hits = _column_scores(body)
        if col_date is None:
            col_date = max(range(len(date_hits)), key=lambda i: date_hits[i])
            if date_hits[col_date] == 0:
                raise ValueError("no date column found")
        if col_amt is None:
            # Amount = most numeric column that is not the date column.
            order = sorted(range(len(num_hits)), key=lambda i: -num_hits[i])
            col_amt = next((i for i in order if i != col_date
                            and num_hits[i] > 0), None)
            if col_amt is None:
                raise ValueError("no amount column found")
        if col_desc is None:
            widths = [max(len(r[i]) if i < len(r) else 0 for r in body)
                      for i in range(max(len(r) for r in body))]
            col_desc = max((i for i in range(len(widths))
                            if i not in (col_date, col_amt)),
                           key=lambda i: widths[i], default=None)

    out = []
    for row in rows[start:]:
        if len(row) <= max(c for c in (col_date, col_amt) if c is not None):
            continue
        d = _parse_date(row[col_date])
        amt = _parse_amount(row[col_amt])
        if d is None or amt is None:
            continue
        desc = (row[col_desc].strip() if col_desc is not None and
                col_desc < len(row) else "")
        ccy = (row[col_ccy].strip().upper() if col_ccy is not None and
               col_ccy < len(row) else "USD")
        if not re.fullmatch(r"[A-Z]{3}", ccy):
            ccy = "USD"
        out.append(Txn(d, desc, amt, ccy))
    if not out:
        raise ValueError("no parsable (date, amount) rows in CSV")
    return out


# --- detection ---------------------------------------------------------------

def normalize_description(desc: str) -> str:
    """Grouping key: uppercase, digits/punctuation dropped, spaces collapsed."""
    cleaned = re.sub(r"[^A-ZА-ЯІЇЄҐ ]+", " ", desc.upper())
    return re.sub(r"\s+", " ", cleaned).strip()


def _pick_period(median_gap: float) -> int | None:
    period = min(KNOWN_PERIODS, key=lambda p: abs(p - median_gap))
    return period if abs(period - median_gap) <= DATE_TOLERANCE else None


def _next_due(last: dt.date, period: int):
    from . import schedule
    if period in (30, 31):
        return schedule.add_months(last, 1, anchor_day=last.day), "monthly", None
    if period == 365:
        return schedule.add_years(last, 1), "yearly", None
    return last + dt.timedelta(days=period), "custom", period


def detect_recurring(txns: list[Txn], min_occurrences: int = MIN_OCCURRENCES,
                     tol: int = DATE_TOLERANCE) -> list[dict]:
    """Find repeating charges -> confirmation candidates (sorted by amount)."""
    groups: dict[str, list[Txn]] = {}
    for t in txns:
        groups.setdefault(normalize_description(t.description), []).append(t)

    candidates = []
    for group in groups.values():
        if len(group) < min_occurrences:
            continue
        group.sort(key=lambda t: t.date)
        gaps = [(b.date - a.date).days for a, b in zip(group, group[1:])]
        period = _pick_period(statistics.median(gaps))
        # Calendar-honest intervals: a monthly charge may gap 28/30/31 days,
        # so each gap may match ANY known period within the tolerance, while
        # the median still picks the labelling period (30 vs 31 etc.).
        if period is None or not all(any(abs(g - p) <= tol
                                         for p in KNOWN_PERIODS) for g in gaps):
            continue
        amounts = [abs(t.amount) for t in group]
        med_amount = statistics.median(amounts)
        if max(amounts) - min(amounts) > max(0.02, AMOUNT_TOLERANCE * med_amount):
            continue
        currencies = [t.currency for t in group]
        ccy = max(set(currencies), key=currencies.count).upper()
        if not re.fullmatch(r"[A-Z]{3}", ccy):
            ccy = "USD"
        next_due, cycle, custom_days = _next_due(group[-1].date, period)
        labels = [t.description.strip() for t in group]
        candidates.append({
            "name": max(set(labels), key=labels.count)[:60],
            "description": max(set(labels), key=labels.count),
            "amount": round(med_amount, 2),
            "currency": ccy,
            "cycle": cycle,
            "custom_days": custom_days,
            "next_due_date": next_due.isoformat(),
            "occurrences": len(group),
            "period_days": period,
            "first_date": group[0].date.isoformat(),
            "last_date": group[-1].date.isoformat(),
        })
    return sorted(candidates, key=lambda c: -c["amount"])
