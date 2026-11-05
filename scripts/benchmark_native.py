#!/usr/bin/env python3
"""Benchmark: recurring-payment detection, Python path vs native C# (SubRec).

Generates a synthetic 50 000-row bank statement (deterministic seed), then
times four variants:

  1. python_parse+detect — csvimport.parse_csv() + csvimport.detect_recurring()
  2. python_detect_only  — detect_recurring() on pre-parsed rows
  3. native_end_to_end   — SubRec.exe subprocess (own parse + detect)
  4. native_accel        — backend/native_accel.parse_and_detect() (Python
                           parse + native detect, the integration path)

Usage: python scripts/benchmark_native.py [--rows 50000] [--repeat 3]
Prints a JSON result to stdout. Requires the native build for variants 3-4
(dotnet publish dotnet/SubRec -c Release -o dotnet/publish); missing exe
skips them instead of failing.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import random
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend import csvimport, native_accel  # noqa: E402

RECURRING = [
    "NETFLIX.COM 8812", "SPOTIFY PARIS", "GYM IRON MONTHLY", "Apple.Com/Bill",
    "ADOBE SYSTEMS", "YOUTUBEPREMIUM", "AMAZON PRIME", "HBOMAX NOW",
    "DISNEY PLUS", "OFFICE 365 SUB", "ICLOUD STORAGE", "DROPBOX PLUS",
    "GOOGLE ONE 2TB", "NOTION LABS", "FIGMA ORG", "CANVA PRO",
    "CHEGG STUDY", "DUOLINGO PLUS", "ENDNOTE SUB", "GITHUB COPilot",
]


def generate(rows: int, seed: int = 20261105) -> str:
    """Synthetic statement: recurring streams + one-off noise, shuffled."""
    rng = random.Random(seed)
    d0 = dt.date(2024, 1, 1)
    out = ["Date,Description,Amount,Currency"]
    rec_rows = int(rows * 0.08)          # ~8% of rows belong to recurring groups
    per_merchant = max(3, rec_rows // len(RECURRING))
    for m in RECURRING:
        period = 30 if "MONTHLY" in m.upper() else rng.choice((7, 14, 30, 31, 365))
        amt = round(rng.uniform(5, 120), 2)
        start = rng.randint(0, 60)
        for k in range(per_merchant):
            day = d0 + dt.timedelta(days=start + k * period + rng.choice((0, 0, 1, -1)))
            out.append(f"{day.isoformat()},{m},{amt:.2f},USD")
    n_rec = len(out) - 1
    for _ in range(rows - n_rec):
        day = d0 + dt.timedelta(days=rng.randint(0, 500))
        out.append(f"{day.isoformat()},SHOP {rng.randint(1, 10**7)},"
                   f"{rng.uniform(-600, 600):.2f},{rng.choice(('USD', 'UAH', 'EUR'))}")
    body = out[1:]
    rng.shuffle(body)
    return "\n".join([out[0], *body]) + "\n"


def timeit(fn, *args, repeat: int):
    times, result = [], None
    for _ in range(repeat):
        t0 = time.perf_counter()
        result = fn(*args)
        times.append(time.perf_counter() - t0)
    return min(times), result  # type: ignore[return-value]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=50_000)
    ap.add_argument("--repeat", type=int, default=3)
    args = ap.parse_args()

    csv_text = generate(args.rows)
    n_lines = csv_text.count("\n") - 1
    res = {"rows": n_lines, "repeat": args.repeat, "timings_s": {}}

    txns = csvimport.parse_csv(csv_text)
    t_py_both, _ = timeit(lambda: csvimport.detect_recurring(csvimport.parse_csv(csv_text)),
                          repeat=args.repeat)
    t_py_detect, cands = timeit(csvimport.detect_recurring, txns, repeat=args.repeat)
    res["timings_s"]["python_parse+detect"] = round(t_py_both, 3)
    res["timings_s"]["python_detect_only"] = round(t_py_detect, 3)
    res["candidates"] = len(cands)

    exe = native_accel.native_exe()
    if exe is None:
        print(json.dumps(res, indent=2))
        print("native exe not found — native variants skipped", file=sys.stderr)
        return 0

    t_native, native_out = timeit(
        lambda: (lambda p: p.stdout)(subprocess.run(
            [str(exe)], input=csv_text, capture_output=True, encoding="utf-8")),
        repeat=args.repeat)
    t_accel, accel_cands = timeit(native_accel.parse_and_detect, csv_text,
                                  repeat=args.repeat)
    assert native_out is not None
    native_obj = json.loads(native_out)
    res["timings_s"]["native_end_to_end"] = round(t_native, 3)
    res["timings_s"]["native_accel_parse+detect"] = round(t_accel, 3)
    res["native_parity"] = (native_obj["candidates"] == cands
                            and native_obj["rows"] == len(txns))
    res["native_candidates"] = len(native_obj["candidates"])
    res["speedup_end_to_end"] = round(t_py_both / t_native, 1)
    res["speedup_detect_only"] = round(t_py_detect / t_native, 1)
    print(json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
