# Spending trends по місяцях: фактичні списання за ОСТАННІ N місяців
# (дзеркало projection.py, який дивиться вперед), помісячні суми по валюті,
# середнє за період і зміна останній-місяць-проти-середнього.
from __future__ import annotations

import calendar
import datetime as dt


def _month_start(y: int, m: int) -> dt.date:
    return dt.date(y, m, 1)


def prev_month(y: int, m: int) -> tuple[int, int]:
    return (y - 1, 12) if m == 1 else (y, m - 1)


def bucket_labels(today: dt.date, months: int) -> list[str]:
    """Останні `months` місяців, включно з поточним: '2026-09', '2026-10',
    '2026-11' для today=2026-11-05 і months=3."""
    y, m = today.year, today.month
    out = []
    for _ in range(months):
        out.append(f"{y:04d}-{m:02d}")
        y, m = prev_month(y, m)
    return list(reversed(out))


def previous_due(due: dt.date, cycle: str, custom_days: int | None,
                 anchor_day: int | None = None) -> dt.date:
    """Списання НА ОДИН цикл раніше за `due` (дзеркало schedule.next_due_date)."""
    from . import schedule
    if cycle == "monthly":
        y, m = prev_month(due.year, due.month)
        return schedule._clamp(y, m, anchor_day or due.day)
    if cycle == "yearly":
        return schedule._clamp(due.year - 1, due.month, anchor_day or due.day)
    if cycle == "custom":
        if not custom_days or custom_days <= 0:
            raise ValueError("custom cycle needs a positive custom_days")
        return due - dt.timedelta(days=custom_days)
    raise ValueError(f"unknown cycle {cycle!r}")


def past_occurrences(next_due: dt.date, cycle: str, custom_days: int | None,
                     window_start: dt.date, today: dt.date,
                     anchor_day: int | None = None) -> list[dt.date]:
    """Фактичні списання у вікні [window_start, today), рухаючись назад
    від збереженого next_due_date. today не включається (ще не списали)."""
    out = []
    d = next_due
    for _ in range(2400):          # той самий захист від зіпсованих даних
        if d < today:
            break
        d = previous_due(d, cycle, custom_days, anchor_day)
    else:
        return []
    while d >= window_start:
        out.append(d)
        d = previous_due(d, cycle, custom_days, anchor_day)
    return list(reversed(out))


def monthly_trends(rows, today: dt.date | None = None,
                   months: int = 6) -> list[dict]:
    """Помісячні суми ФАКТИЧНИХ списань за останні `months` місяців.

    rows: subscription rows (sqlite3.Row-подібні). Призупинені (paused)
    пропускаються. Валюти ніколи не змішуються — окремі totals per currency.
    """
    today = today or dt.date.today()
    labels = bucket_labels(today, months)
    if months <= 0 or not rows:
        return [{"month": lb, "totals": {}} for lb in labels]
    # window_start = перший день першого місяця вікна
    y0, m0 = today.year, today.month
    for _ in range(months - 1):
        y0, m0 = prev_month(y0, m0)
    window_start = _month_start(y0, m0)

    totals: list[dict[str, float]] = [{} for _ in range(months)]
    for r in rows:
        if "paused" in r.keys() and r["paused"]:
            continue
        start = dt.date.fromisoformat(r["next_due_date"])
        anchor = r["anchor_day"] if "anchor_day" in r.keys() else None
        for d in past_occurrences(start, r["cycle"], r["custom_days"],
                                  window_start, today, anchor):
            idx = months - 1
            yy, mm = today.year, today.month
            while (yy, mm) != (d.year, d.month):
                yy, mm = prev_month(yy, mm)
                idx -= 1
                if idx < 0:
                    break
            if 0 <= idx < months:
                ccy = r["currency"]
                totals[idx][ccy] = totals[idx].get(ccy, 0.0) + r["amount"]
    return [{"month": lb, "totals": {k: round(v, 2) for k, v in t.items()}}
            for lb, t in zip(labels, totals)]


def trend_summary(trends: list[dict]) -> dict:
    """Агрегат по вікну: середнє/сумарно по валютах + порівняння останнього
    місяця з середнім (тренд up/down/flat, поріг ±5%). Валюти не змішуються."""
    grand: dict[str, float] = {}
    for b in trends:
        for ccy, v in b["totals"].items():
            grand[ccy] = grand.get(ccy, 0.0) + v
    n = len(trends)
    per_currency = {}
    for ccy, total in grand.items():
        avg = total / n if n else 0.0
        last = trends[-1]["totals"].get(ccy, 0.0) if trends else 0.0
        delta_pct = ((last - avg) / avg * 100) if avg else 0.0
        per_currency[ccy] = {
            "monthly_average": round(avg, 2),
            "window_total": round(total, 2),
            "last_month": round(last, 2),
            "delta_pct": round(delta_pct, 1),
            "direction": ("up" if delta_pct > 5 else
                          "down" if delta_pct < -5 else "flat"),
        }
    return {"months": [b["month"] for b in trends], "per_currency": per_currency}
