# Family mode: who owns a subscription, who pays for it, and what share of
# the cost belongs to each payer. Currencies are never mixed.
from __future__ import annotations

from collections import defaultdict


def family_breakdown(rows) -> dict:
    """Group active subscriptions by payer (NULL payer -> '(не вказано)').

    Each payer gets their share-adjusted monthly/yearly totals per currency
    (share_pct of the monthly equivalent) plus the list of subscriptions.
    """
    payers: dict[str, dict] = {}
    for r in rows:
        payer = r["payer"] or "(не вказано)"
        bucket = payers.setdefault(payer, {
            "payer": payer,
            "monthly_by_currency": defaultdict(float),
            "yearly_by_currency": {},
            "subscriptions": [],
        })
        me = r["monthly_equivalent"] if "monthly_equivalent" in r.keys() else None
        if me is None:
            from . import schedule
            me = schedule.monthly_equivalent(r["amount"], r["cycle"],
                                             r["custom_days"])
        share = (r["share_pct"] if r["share_pct"] is not None else 100) / 100.0
        ccy = r["currency"]
        bucket["monthly_by_currency"][ccy] += me * share
        bucket["subscriptions"].append({
            "id": r["id"],
            "name": r["name"],
            "owner": r["owner"] if "owner" in r.keys() else None,
            "payer": payer,
            "share_pct": r["share_pct"] if r["share_pct"] is not None else 100,
            "amount": r["amount"],
            "currency": ccy,
        })

    out = []
    for payer in sorted(payers):
        b = payers[payer]
        monthly = {k: round(v, 2) for k, v in sorted(b["monthly_by_currency"].items())}
        yearly = {k: round(v * 12, 2) for k, v in monthly.items()}
        out.append({
            "payer": payer,
            "subscription_count": len(b["subscriptions"]),
            "monthly_by_currency": monthly,
            "yearly_by_currency": yearly,
            "subscriptions": b["subscriptions"],
        })
    return {"payers": out}
