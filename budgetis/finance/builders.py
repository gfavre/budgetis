from __future__ import annotations

from decimal import ROUND_HALF_UP
from decimal import Decimal
from typing import TYPE_CHECKING

from django.db.models import QuerySet
from django.db.models import Sum
from django.utils.translation import gettext_lazy as _


if TYPE_CHECKING:
    from budgetis.accounting.models import Account

# ----- Constants -------------------------------------------------------------

REVENUE_NATURE_RANGE = (400, 499)
IMPOTS_NATURE_RANGE = (400, 409)
IMPOTS_NATURE_EXCLUDE = (402, 404, 405)
TAXES_NATURE_RANGE = (430, 439)
RENTALS_NATURE = (423, 427)

COLOR_IMPOTS = "#2066CF"
COLOR_RANDOM = "#5B8DEF"
COLOR_TAXES = "#F59E0B"
COLOR_RENTALS = "#2BB673"
COLOR_OTHERS = "#6B7280"
COLOR_BUDGET = "#111827"


def _fmt_chf_short(value: Decimal) -> str:
    """Return CHF amount with K/M suffix."""
    v = value.copy_abs()
    if v >= Decimal("1000000"):
        n = (v / Decimal("1000000")).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        return f"CHF{n}M"
    n = (v / Decimal("1000")).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
    return f"CHF{n}K"


def _compute_bucket_sums(qs: QuerySet[Account]) -> dict[str, Decimal]:
    """Sum revenues per bucket (no merge)."""
    base = qs.filter(nature__range=REVENUE_NATURE_RANGE)
    impots = base.filter(nature__range=IMPOTS_NATURE_RANGE).exclude(nature__in=IMPOTS_NATURE_EXCLUDE).aggregate(
        v=Sum("revenues")
    )["v"] or Decimal("0")
    randoms = base.filter(nature__in=IMPOTS_NATURE_EXCLUDE).aggregate(v=Sum("revenues"))["v"] or Decimal("0")
    taxes = base.filter(nature__range=TAXES_NATURE_RANGE).aggregate(v=Sum("revenues"))["v"] or Decimal("0")
    rentals = base.filter(nature__in=RENTALS_NATURE).aggregate(v=Sum("revenues"))["v"] or Decimal("0")
    others = base.exclude(nature__range=IMPOTS_NATURE_RANGE).exclude(nature__range=TAXES_NATURE_RANGE).exclude(
        nature__in=RENTALS_NATURE
    ).aggregate(v=Sum("revenues"))["v"] or Decimal("0")
    return {"impots": impots, "randoms": randoms, "taxes": taxes, "rentals": rentals, "others": others}


def build_income_buckets_to_budget(qs: QuerySet[Account]) -> dict[str, list[dict[str, object]]]:
    """
    Build 'income buckets -> Budget' with a fixed vertical order (no sorting).
    Order: Impôts, Random taxes, Taxes, Rentals, Other revenues -> Budget.
    """
    sums = _compute_bucket_sums(qs)
    impots = max(Decimal("0"), sums["impots"])
    randoms = max(Decimal("0"), sums["randoms"])
    taxes = max(Decimal("0"), sums["taxes"])
    rentals = max(Decimal("0"), sums["rentals"])
    others = max(Decimal("0"), sums["others"])
    budget = impots + randoms + taxes + rentals + others

    labels = [
        str(_("Impôts")),  # 0
        str(_("Revenus aléatoires")),  # 1
        str(_("Taxes")),  # 2
        str(_("Locations")),  # 3
        str(_("Autres revenus")),  # 4
        str(_("Budget")),  # 5
    ]
    nodes = [{"name": n} for n in labels]
    node_colors = [COLOR_IMPOTS, COLOR_RANDOM, COLOR_TAXES, COLOR_RENTALS, COLOR_OTHERS, COLOR_BUDGET]

    # Fixed positions (match order above)
    node_x: list[float] = [0.0, 0.0, 0.0, 0.0, 0.0, 0.68]
    node_y: list[float] = [0.05, 0.18, 0.33, 0.50, 0.70, 0.35]

    links = [
        {"source": 0, "target": 5, "value": float(impots), "color": COLOR_IMPOTS},
        {"source": 1, "target": 5, "value": float(randoms), "color": COLOR_RANDOM},
        {"source": 2, "target": 5, "value": float(taxes), "color": COLOR_TAXES},
        {"source": 3, "target": 5, "value": float(rentals), "color": COLOR_RENTALS},
        {"source": 4, "target": 5, "value": float(others), "color": COLOR_OTHERS},
    ]
    links = [link for link in links if link["value"] > 0]

    annotations = [
        {
            "x": node_x[0],
            "y": node_y[0],
            "xref": "paper",
            "yref": "paper",
            "showarrow": False,
            "xanchor": "right",
            "text": f"{labels[0]}<br><b>{_fmt_chf_short(impots)}</b>",
        },
        {
            "x": node_x[1],
            "y": node_y[1],
            "xref": "paper",
            "yref": "paper",
            "showarrow": False,
            "xanchor": "right",
            "text": f"{labels[1]}<br><b>{_fmt_chf_short(randoms)}</b>",
        },
        {
            "x": node_x[2],
            "y": node_y[2],
            "xref": "paper",
            "yref": "paper",
            "showarrow": False,
            "xanchor": "right",
            "text": f"{labels[2]}<br><b>{_fmt_chf_short(taxes)}</b>",
        },
        {
            "x": node_x[3],
            "y": node_y[3],
            "xref": "paper",
            "yref": "paper",
            "showarrow": False,
            "xanchor": "right",
            "text": f"{labels[3]}<br><b>{_fmt_chf_short(rentals)}</b>",
        },
        {
            "x": node_x[4],
            "y": node_y[4],
            "xref": "paper",
            "yref": "paper",
            "showarrow": False,
            "xanchor": "right",
            "text": f"{labels[4]}<br><b>{_fmt_chf_short(others)}</b>",
        },
        {
            "x": node_x[5],
            "y": node_y[5],
            "xref": "paper",
            "yref": "paper",
            "showarrow": False,
            "xanchor": "center",
            "text": f"{labels[5]}<br><b>{_fmt_chf_short(budget)}</b>",
        },
    ]

    return {
        "nodes": nodes,
        "links": [{"source": link["source"], "target": link["target"], "value": link["value"]} for link in links],
        "link_colors": [link["color"] for link in links],
        "node_colors": node_colors,
        "node_x": node_x,
        "node_y": node_y,
        "annotations": annotations,
    }
