# Multi-currency support: daily reference rates from the ECB (eurofxref).
#
# Design: fetch once, cache to disk (TTL), and fall back to the stale cache
# when the network is unreachable — a local-first tool must keep working
# offline. Rates are EUR-based ("units of currency per 1 EUR"), matching the
# ECB feed; EUR itself is always 1.0.
from __future__ import annotations

import datetime as dt
import json
import os
import urllib.request
import xml.etree.ElementTree as ET

ECB_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
CACHE_TTL_HOURS = 12


def cache_path() -> str:
    env = os.environ.get("SUBWATCH_RATES_CACHE")
    if env:
        return env
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, "rates_cache.json")


def parse_ecb_xml(data: bytes) -> dict[str, float]:
    """Extract EUR-based rates from the eurofxref daily XML."""
    rates = {"EUR": 1.0}
    for el in ET.fromstring(data).iter():
        if el.tag.rsplit("}", 1)[-1] == "Cube" and "currency" in el.attrib:
            rates[el.attrib["currency"]] = float(el.attrib["rate"])
    if len(rates) <= 1:
        raise ValueError("no rates found in ECB XML")
    return rates


def fetch_rates(timeout: int = 10) -> dict[str, float]:
    with urllib.request.urlopen(ECB_URL, timeout=timeout) as resp:
        return parse_ecb_xml(resp.read())


def _read_cache(path: str) -> dict[str, float] | None:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)["rates"]
    except (OSError, KeyError, ValueError):
        return None


def _write_cache(path: str, rates: dict[str, float]) -> None:
    tmp = {"fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(),
           "rates": rates}
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(tmp, f)
    except OSError:
        pass  # a broken cache must never break the fetch path


def get_rates(fetcher=None, cache: str | None = None,
              max_age_hours: int = CACHE_TTL_HOURS) -> dict[str, float]:
    """Fresh ECB rates, or the last cached set when offline. {} if never cached.

    The TTL is deliberately soft: a stale rate is better than no rate for a
    purely informational summary.
    """
    fetcher = fetcher or fetch_rates  # resolved at call time (patchable in tests)
    path = cache or cache_path()
    try:
        rates = fetcher()
    except Exception:
        return _read_cache(path) or {}
    _write_cache(path, rates)
    return rates


def convert(amount: float, from_ccy: str, to_ccy: str,
            rates: dict[str, float]) -> float | None:
    """Cross-rate conversion through the EUR base (ECB quoting convention)."""
    if not rates or from_ccy not in rates or to_ccy not in rates:
        return None
    if from_ccy == to_ccy:
        return amount
    return amount / rates[from_ccy] * rates[to_ccy]
