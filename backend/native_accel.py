# Optional C# accelerator for recurring-payment detection.
#
# The SubRec CLI (dotnet/SubRec, see dotnet/README.md) is a faithful port of
# csvimport.parse_csv() + csvimport.detect_recurring(). When its executable is
# available this module runs the whole CSV -> candidates pipeline through it;
# otherwise — or if the native call fails for any reason — it silently falls
# back to the pure-Python path. Both paths produce IDENTICAL candidates on the
# same input (golden-verified by tests/test_native_parity.py).
from __future__ import annotations

import csv
import io
import json
import os
import subprocess
from pathlib import Path

from . import csvimport
from .csvimport import Txn, detect_recurring as _py_detect
from .csvimport import parse_csv as _py_parse

_TIMEOUT_S = 120


def _env_disabled() -> bool:
    v = os.environ.get("SUBWATCH_NATIVE", "").strip().lower()
    return v in ("0", "off", "false", "no")


def _default_candidates():
    # Default: the self-contained publish output next to the repo root.
    root = Path(__file__).resolve().parent.parent / "dotnet" / "publish"
    yield root / "SubRec.exe"
    yield root / "SubRec"


def native_exe() -> Path | None:
    """Path to the native accelerator executable, or None when unavailable.

    An explicit SUBWATCH_NATIVE path is authoritative: when it does not exist
    the native path is considered off (set it to 'off' or a missing path to
    force the pure-Python route). Unset, it defaults to dotnet/publish/.
    """
    if _env_disabled():
        return None
    env = os.environ.get("SUBWATCH_NATIVE", "").strip()
    if env:
        p = Path(env)
        return p if p.is_file() else None
    for p in _default_candidates():
        if p.is_file():
            return p
    return None


def native_available() -> bool:
    return native_exe() is not None


def _csv_field(value: str) -> str:
    if any(c in value for c in (",", '"', "\n", "\r")):
        return '"' + value.replace('"', '""').replace("\n", " ").replace("\r", " ") + '"'
    return value


def _txns_to_csv(txns: list[Txn]) -> str:
    """Serialize parsed transactions into the CLI's canonical CSV input."""
    buf = io.StringIO()
    buf.write("date,description,amount,currency\n")
    for t in txns:
        # repr(float) is the shortest round-trip form: the native side parses
        # back the exact same double, so medians/rounding stay identical.
        buf.write(",".join((
            t.date.isoformat(),
            _csv_field(t.description),
            _csv_field(repr(t.amount)),
            _csv_field(t.currency),
        )) + "\n")
    return buf.getvalue()


def _run_native(csv_text: str, min_occurrences: int, tol: int,
                canonical: bool = False) -> dict | None:
    """Run the exe on CSV text. Returns {"rows": n, "candidates": [...]}
    or None on any failure (missing exe, crash, bad output). `canonical`
    selects the CLI's fixed-order input (see _txns_to_csv)."""
    exe = native_exe()
    if exe is None:
        return None
    try:
        args = [str(exe)]
        if canonical:
            args.append("--canonical")
        args += ["--min-occurrences", str(min_occurrences), "--tolerance", str(tol)]
        proc = subprocess.run(
            args, input=csv_text, capture_output=True, encoding="utf-8",
            timeout=_TIMEOUT_S)
        if proc.returncode != 0:
            return None
        out = json.loads(proc.stdout)
        if not (isinstance(out, dict) and isinstance(out.get("rows"), int)
                and _valid_candidates(out.get("candidates"))):
            return None
        return out
    except (OSError, subprocess.SubprocessError, ValueError, json.JSONDecodeError):
        return None


def _valid_candidates(obj) -> list[dict] | None:
    if isinstance(obj, list) and all(isinstance(c, dict) for c in obj):
        return obj
    return None


def detect_recurring(txns: list[Txn], min_occurrences: int = csvimport.MIN_OCCURRENCES,
                     tol: int = csvimport.DATE_TOLERANCE) -> list[dict]:
    """csvimport.detect_recurring(), accelerated by the native CLI when available.

    Accepts already-parsed Txn rows; identical output to the Python path
    (native path serializes the rows back to canonical CSV for the CLI).
    """
    native = _run_native(_txns_to_csv(txns), min_occurrences, tol, canonical=True)
    if native is not None and native["rows"] == len(txns):
        return native["candidates"]
    return _py_detect(txns, min_occurrences, tol)


def parse_and_detect(text: str, preset_name: str | None = None) -> tuple[int, list[dict]]:
    """Full pipeline on raw CSV text -> (parsed_rows, candidates).

    Without a preset the raw CSV goes straight into the native CLI (its own
    parser + detector, no double parsing); bank presets are applied on the
    Python side (the CLI has no preset table) and only detection is
    accelerated. Falls back to the pure-Python pipeline when the exe is
    unavailable or fails.
    """
    if preset_name is None:
        native = _run_native(text, csvimport.MIN_OCCURRENCES, csvimport.DATE_TOLERANCE)
        if native is not None:
            return native["rows"], native["candidates"]
    txns = _py_parse(text, preset_name)
    return len(txns), detect_recurring(txns)
