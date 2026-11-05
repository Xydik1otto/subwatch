# Tag analytics: monthly spend grouped by the free-form `tags` column
# (comma-separated), plus a dependency-free SVG pie chart.
#
# Currencies are never mixed inside a slice: the pie shows the primary
# currency (the one carrying the largest total); everything else is reported
# separately in the JSON endpoint.
from __future__ import annotations

import math

PALETTE = ("#4a6fdc", "#e63946", "#2a9d8f", "#e9c46a", "#9b5de5",
           "#f4a261", "#577590", "#43aa8b", "#f28482", "#6d597a")


def parse_tags(raw: str | None) -> list[str]:
    """'video, music' -> ['video', 'music'] (lowercased, deduplicated)."""
    if not raw:
        return []
    seen: set[str] = set()
    out = []
    for part in raw.split(","):
        t = part.strip().lower()
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def monthly_by_tag(rows) -> list[dict]:
    """Group monthly-equivalent spend by tag: [{tag, monthly_by_currency}].

    A subscription with several tags counts toward each of them; untagged
    subscriptions are aggregated under the tag ''.
    """
    from . import schedule

    acc: dict[str, dict[str, float]] = {}
    for r in rows:
        if "paused" in r.keys() and r["paused"]:
            continue
        me = schedule.monthly_equivalent(r["amount"], r["cycle"],
                                         r["custom_days"])
        for tag in (parse_tags(r["tags"]) or [""]):
            ccy = acc.setdefault(tag, {})
            ccy[r["currency"]] = ccy.get(r["currency"], 0.0) + me
    out = [{"tag": tag,
            "monthly_by_currency": {k: round(v, 2) for k, v in sorted(c.items())}}
           for tag, c in acc.items()]
    return sorted(out, key=lambda d: d["tag"])


def primary_currency(breakdown: list[dict]) -> str | None:
    grand: dict[str, float] = {}
    for t in breakdown:
        for ccy, v in t["monthly_by_currency"].items():
            grand[ccy] = grand.get(ccy, 0.0) + v
    return max(grand, key=lambda c: grand[c]) if grand else None


def _polar(cx: float, cy: float, r: float, angle: float) -> tuple[float, float]:
    return cx + r * math.cos(angle), cy + r * math.sin(angle)


def _slice_path(cx: float, cy: float, r: float, a0: float, a1: float) -> str:
    x0, y0 = _polar(cx, cy, r, a0)
    x1, y1 = _polar(cx, cy, r, a1)
    large = 1 if (a1 - a0) > math.pi else 0
    return (f"M {cx:.2f} {cy:.2f} L {x0:.2f} {y0:.2f} "
            f"A {r:.2f} {r:.2f} 0 {large} 1 {x1:.2f} {y1:.2f} Z")


def build_svg(breakdown: list[dict], ccy: str, width: int = 720,
              height: int = 300, title: str = "Витрати по тегах") -> str:
    """SVG pie: one slice per tag, sized by monthly spend in `ccy`."""
    slices = [(t["tag"], t["monthly_by_currency"].get(ccy, 0.0))
              for t in breakdown]
    slices = [(t, v) for t, v in slices if v > 0]
    total = sum(v for _, v in slices)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" role="img" aria-label="{title} ({ccy})">',
        f"<title>{title} ({ccy})</title>",
        f'<text x="16" y="20" font-size="13" fill="#334">{title} ({ccy})</text>',
    ]
    if not slices:
        parts.append(f'<text x="{width / 2:.0f}" y="{height / 2:.0f}" '
                     'font-size="13" text-anchor="middle" fill="#889">'
                     "немає даних — додайте теги підпискам</text>")
        parts.append("</svg>")
        return "\n".join(parts)

    cx, cy, r = 140.0, height / 2 + 10, 100.0
    angle = -math.pi / 2
    for i, (tag, v) in enumerate(slices):
        sweep = (v / total) * 2 * math.pi
        color = PALETTE[i % len(PALETTE)]
        parts.append(
            f'<path d="{_slice_path(cx, cy, r, angle, angle + sweep)}" '
            f'fill="{color}" stroke="#fff" stroke-width="1.5"><title>'
            f"{tag or '(без тегу)'}: {v:.2f} {ccy}</title></path>")
        angle += sweep

    # legend
    lx, ly = cx + r + 30, cy - len(slices) * 11 + 11
    for i, (tag, v) in enumerate(slices):
        color = PALETTE[i % len(PALETTE)]
        y = ly + i * 22
        parts.append(f'<rect x="{lx}" y="{y - 9:.1f}" width="11" height="11" '
                     f'fill="{color}" rx="2"/>')
        share = v / total * 100 if total else 0.0
        parts.append(f'<text x="{lx + 18}" y="{y + 1:.1f}" font-size="11" '
                     f'fill="#334">{tag or "(без тегу)"} — {v:.2f} {ccy} '
                     f"({share:.1f}%)</text>")
    parts.append("</svg>")
    return "\n".join(parts)
