# Annual projection: per-calendar-month sums of actual charges for the next
# N months, plus a dependency-free SVG bar chart.
from __future__ import annotations

import calendar
import datetime as dt


def _month_start(y: int, m: int) -> dt.date:
    return dt.date(y, m, 1)


def bucket_labels(today: dt.date, months: int) -> list[str]:
    y, m = today.year, today.month
    out = []
    for _ in range(months):
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def monthly_projection(rows, today: dt.date | None = None,
                       months: int = 12) -> list[dict]:
    """Sum of ACTUAL charge amounts per calendar month (not monthly-equivalent).

    rows: subscription rows (sqlite3.Row-like dicts with paused flag support).
    Charges falling outside the last bucket are cut off, not accumulated.
    """
    today = today or dt.date.today()
    labels = bucket_labels(today, months)
    totals = [dict() for _ in range(months)]
    if months <= 0 or not rows:
        return [{"month": lb, "totals": {}} for lb in labels]

    y0, m0 = today.year, today.month
    # 0-based month index of the LAST bucket
    last_year, last_month0 = divmod((m0 - 1) + (months - 1), 12)
    last_year += y0
    last_month = last_month0 + 1
    horizon_end = dt.date(last_year, last_month,
                          calendar.monthrange(last_year, last_month)[1])
    horizon_days = (horizon_end - today).days

    from . import schedule
    for r in rows:
        if "paused" in r.keys() and r["paused"]:
            continue
        start = dt.date.fromisoformat(r["next_due_date"])
        anchor = r["anchor_day"] if "anchor_day" in r.keys() else None
        for d in schedule.upcoming_dates(start, r["cycle"], r["custom_days"],
                                         horizon_days, today, anchor):
            idx = (d.year - y0) * 12 + (d.month - m0)
            if 0 <= idx < months:
                ccy = r["currency"]
                totals[idx][ccy] = totals[idx].get(ccy, 0.0) + r["amount"]
    return [{"month": lb, "totals": {k: round(v, 2) for k, v in t.items()}}
            for lb, t in zip(labels, totals)]


def primary_currency(projection: list[dict]) -> str | None:
    """The currency carrying the largest total over the whole horizon."""
    grand: dict[str, float] = {}
    for b in projection:
        for ccy, v in b["totals"].items():
            grand[ccy] = grand.get(ccy, 0.0) + v
    return max(grand, key=lambda c: grand[c]) if grand else None


def build_svg(projection: list[dict], ccy: str, width: int = 760,
              height: int = 280, title: str = "Projection: 12 months") -> str:
    """Minimal SVG bar chart: one bar per month, value + month labels."""
    values = [b["totals"].get(ccy, 0.0) for b in projection]
    labels = [b["month"][2:] for b in projection]  # '26-11'
    x0, y0 = 46, 30
    plot_w, plot_h = width - x0 - 20, height - y0 - 48
    vmax = max(values, default=0.0) or 1.0
    n = max(len(values), 1)
    slot = plot_w / n
    bar_w = slot * 0.62

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" role="img" aria-label="{title} {ccy}">',
        f"<title>{title} ({ccy})</title>",
        f"<text x=\"{x0}\" y=\"18\" font-size=\"13\" fill=\"#334\">"
        f"{title} ({ccy})</text>",
        # baseline
        f'<line x1="{x0}" y1="{y0 + plot_h}" x2="{x0 + plot_w}" '
        f'y2="{y0 + plot_h}" stroke="#889" stroke-width="1"/>',
    ]
    for i, (v, lb) in enumerate(zip(values, labels)):
        h = plot_h * (v / vmax) if v > 0 else 0
        x = x0 + i * slot + (slot - bar_w) / 2
        y = y0 + plot_h - h
        parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" '
            f'height="{h:.1f}" fill="#4a6fdc" rx="3"><title>'
            f"{projection[i]['month']}: {v:.2f} {ccy}</title></rect>")
        parts.append(
            f'<text x="{x + bar_w / 2:.1f}" y="{y - 4:.1f}" '
            f'font-size="10" text-anchor="middle" fill="#334">'
            f"{v:.0f}</text>")
        parts.append(
            f'<text x="{x + bar_w / 2:.1f}" y="{y0 + plot_h + 14:.1f}" '
            f'font-size="10" text-anchor="middle" fill="#556">{lb}</text>')
    parts.append("</svg>")
    return "\n".join(parts)
