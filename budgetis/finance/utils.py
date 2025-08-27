from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING
from typing import Literal

from django.db.models import QuerySet
from django.db.models import Sum
from django.utils.translation import gettext_lazy as _


if TYPE_CHECKING:
    from collections.abc import Iterable

    from budgetis.accounting.models import Account


GroupBy = Literal["group", "function_nature"]
ValueMode = Literal["net", "charges", "revenues"]

# Revenus = xxx.4xx
# Charges = xxx.3xx
# Impots: 210.4xx
# impôts aléatoires: 210.402 (impôt foncier), 210.404 (droits de mutation), 210.405 (successions)

RENTALS_NATURE = 423
TAXES_NATURE = 434


def _fmt_fn(function: int, nature: int) -> str:
    """
    Format function.nature code as 'FFF.NNN'.

    Args:
        function: Function part (e.g., 170).
        nature: Nature part (e.g., 303).

    Returns:
        Zero-padded function.nature string.
    """
    return f"{function:03d}.{nature:03d}"


def build_sankey_data(  # noqa: PLR0912, C901
    qs: QuerySet[Account],
    *,
    group_by: GroupBy = "group",
    value_mode: ValueMode = "net",
    min_amount: Decimal = Decimal("0"),
) -> dict[str, list[dict[str, object]]]:
    """
    Build nodes/links for a Sankey diagram from Account rows.

    Args:
        qs: Base queryset of Account already filtered (year, is_budget, etc.).
        group_by: Aggregation level ("group" or "function_nature").
        value_mode: Which value to use for link magnitude: "net", "charges", "revenues".
        min_amount: Ignore absolute amounts below this threshold (after sign handling).

    Returns:
        A dict with "nodes" and "links" arrays, compatible with Plotly Sankey.
    """
    # Aggregate amounts per key
    if group_by == "group":
        annotated = (
            qs.values("group_id", "group__label")
            .annotate(
                total_charges=Sum("charges"),
                total_revenues=Sum("revenues"),
            )
            .order_by("group__label")
        )
        key_label_pairs: Iterable[tuple[str, str]] = (
            (f"group:{row['group_id']}", row["group__label"]) for row in annotated
        )
        totals_lookup: dict[str, tuple[Decimal, Decimal]] = {
            f"group:{row['group_id']}": (
                row["total_charges"] or Decimal("0"),
                row["total_revenues"] or Decimal("0"),
            )
            for row in annotated
        }
    else:
        annotated = (
            qs.values("function", "nature")
            .annotate(
                total_charges=Sum("charges"),
                total_revenues=Sum("revenues"),
            )
            .order_by("function", "nature")
        )
        key_label_pairs = (
            (f"fn:{row['function']}.{row['nature']}", _fmt_fn(row["function"], row["nature"])) for row in annotated
        )
        totals_lookup = {
            f"fn:{row['function']}.{row['nature']}": (
                row["total_charges"] or Decimal("0"),
                row["total_revenues"] or Decimal("0"),
            )
            for row in annotated
        }

    # Nodes: a virtual source for revenues and a virtual sink for charges
    # Links: revenues -> node ; node -> charges (or a single net flow if value_mode="net")
    nodes: list[dict[str, object]] = []
    links: list[dict[str, object]] = []

    def add_node(label: str) -> int:
        """Return index of node, creating it if necessary."""
        if label not in node_index:
            node_index[label] = len(nodes)
            nodes.append({"name": label})
        return node_index[label]

    node_index: dict[str, int] = {}
    src_revenues_idx = add_node(_("Revenues"))
    sink_charges_idx = add_node(_("Charges"))

    # Add intermediate nodes for each key
    key_to_idx: dict[str, int] = {}
    for key, label in key_label_pairs:
        key_to_idx[key] = add_node(label)

    # Build links according to value mode
    for key, (total_charges, total_revenues) in totals_lookup.items():
        node_idx = key_to_idx[key]

        if value_mode == "net":
            net = (total_revenues or 0) - (total_charges or 0)
            amount = abs(net)
            if amount < min_amount or amount == 0:
                continue
            if net >= 0:
                links.append({"source": src_revenues_idx, "target": node_idx, "value": float(amount)})
            else:
                links.append({"source": node_idx, "target": sink_charges_idx, "value": float(amount)})

        elif value_mode in ("revenues", "charges"):
            rev = total_revenues or Decimal("0")
            chg = total_charges or Decimal("0")

            if value_mode in ("revenues",):
                if rev >= min_amount and rev > 0:
                    links.append({"source": src_revenues_idx, "target": node_idx, "value": float(rev)})
            if value_mode in ("charges",):
                if chg >= min_amount and chg > 0:
                    links.append({"source": node_idx, "target": sink_charges_idx, "value": float(chg)})

    return {"nodes": nodes, "links": links}
