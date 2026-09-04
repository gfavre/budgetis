from __future__ import annotations

from decimal import ROUND_HALF_UP
from decimal import Decimal
from decimal import InvalidOperation
from typing import TYPE_CHECKING

from django.utils.translation import gettext_lazy as _

from .models import SankeyCategory
from .models import SankeyFlow
from .rules import aggregate_by_category


if TYPE_CHECKING:
    from django.db.models import QuerySet

    from budgetis.accounting.models import Account

# ----- Constants -------------------------------------------------------------
# Only the diagram's fixed structure (the four hubs, and the result/profit/loss
# handling) stays as code. Every leaf category (Salaires, AISGE, Péréquation...)
# is now data - see SankeyCategory and its rule models.
MIN_VAL = 0.5

COLOR_BUDGET = "#555555"
COLOR_BUDGET_LINKS = "#888888"

COLOR_CANTON = "#447B30"
COLOR_CANTON_LINKS = "#6DA44D"

COLOR_INTERCOS = "#B55239"
COLOR_INTERCOS_LINKS = "#CD6E4D"

COLOR_COMMUNE = "#D4AF37"
COLOR_COMMUNE_LINKS = "#E7C970"

COLOR_PROFIT = "#447B30"
COLOR_RESULT = "#000000"

LABEL_HOUSEHOLD = _("Municipal household")
LABEL_CANTON = _("Canton")
LABEL_INTERCOMMUNALITIES = _("Intercommunalities")
LABEL_COMMUNE = _("Commune")
LABEL_RESULT_HUB = _("Result")
LABEL_PROFIT = _("Profit")
LABEL_LOSS = _("Loss")

# SankeyMATIC exports a plain-text format for an external tool, always in
# French, independent of the app's own active language - kept separate from
# the translatable LABEL_* constants above, which drive the in-app Plotly view.
SM_LABEL_HOUSEHOLD = "Ménage communal"
SM_LABEL_CANTON = "Canton"
SM_LABEL_INTERCOMMUNALITIES = "Intercommunalités"
SM_LABEL_COMMUNE = "Commune"
SM_LABEL_PROFIT = "Bénéfice"
SM_LABEL_LOSS = "Perte"

NODE_HOUSEHOLD = "household"
NODE_CANTON = "canton"
NODE_INTERCOS = "intercommunities"
NODE_COMMUNE = "commune"
NODE_RESULT = "result"
KEY_PROFIT = "profit"

# ----- SankeyMATIC export settings --------------------------------------------

SM_SETTINGS = """\
=== Settings ===
size w 1200
 h 1020
margin l 12
 r 12
 t 19
 b 20
bg color #ffffff
 transparent Y
node w 20
 h 40.5
 spacing 61.5
 border 2
 theme a
 color #888888
 opacity 1
flow curvature 0.5
 inheritfrom source
 color #999999
 opacity 0.45
layout order automatic
 justifyorigins N
 justifyends N
 reversegraph N
 attachincompletesto nearest
labels color #000000
 hide N
 highlight 0.65
 fontface sans-serif
 linespacing 0.2
 relativesize 109
 magnify 119
labelname appears Y
 size 18
 weight 400
labelvalue appears Y
 fullprecision Y
 position below
 weight 400
labelposition autoalign 0
 scheme per_stage
 first before
 breakpoint 4
value format ' .'
 prefix 'CHF'
 suffix 'K'
themeoffset a 3
 b 2
 c 0
 d 0
meta mentionsankeymatic N
 listimbalances Y"""


def to_rounded_float(val, q: str = "0.01") -> float:
    """
    Force val en Decimal, arrondi selon `q` (par défaut aux centimes),
    puis convertit en float pour Plotly.
    """
    if val is None:
        return 0.0
    if not isinstance(val, Decimal):
        try:
            val = Decimal(str(val))
        except InvalidOperation:
            return 0.0
    return float(val.quantize(Decimal(q), rounding=ROUND_HALF_UP))


def _fmt_chf_short(value: Decimal) -> str:
    """Return CHF amount with K/M suffix."""
    v = value.copy_abs()
    if v >= Decimal("1000000"):
        n = (v / Decimal("1000000")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return f"CHF{n}M"
    n = (v / Decimal("1000")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"CHF{n}K"


def _node_label(label: str, val: Decimal) -> str:
    return f"<sub>{label}</sub><br>{_fmt_chf_short(val)}" if val > 0 else label


def _push_node(  # noqa: PLR0913
    idx: dict[str, int],
    labels: list[str],
    nodes: list[dict[str, str]],
    node_colors: list[str],
    key: str,
    label: str,
    value: Decimal,
    color: str,
) -> None:
    """Append a node with a stable key and a formatted label; update color & index map."""
    value = Decimal("0") if value is None else Decimal(str(value))
    name = _node_label(str(label), value)
    idx[key] = len(labels)
    labels.append(name)
    nodes.append({"name": name})
    node_colors.append(color)


def _add_link(  # noqa: PLR0913
    idx: dict[str, int],
    links: list[dict[str, float]],
    link_colors: list[str],
    src_key: str,
    dst_key: str,
    value: Decimal,
    color: str,
) -> None:
    """Add a link if value > 0, using stable node keys."""
    if value and value > 0:
        links.append({"source": idx[src_key], "target": idx[dst_key], "value": float(value)})
        link_colors.append(color)


def _category_totals(qs: QuerySet[Account], scheme: str) -> dict[str, list[tuple[SankeyCategory, Decimal]]]:
    """
    Resolves every account to its Sankey category, sums charges/revenues per
    category, and groups the result by flow block (all categories of a flow
    are included even at zero, so the diagram's shape stays stable year to
    year regardless of which buckets happen to carry money).
    """
    totals = aggregate_by_category(qs, scheme)
    field_by_flow: dict[str, str] = {
        SankeyFlow.REVENUE: "revenues",
        SankeyFlow.CANTON: "charges",
        SankeyFlow.INTERCOMMUNALITY: "charges",
        SankeyFlow.COMMUNE: "charges",
        SankeyFlow.DOTATION: "charges",
    }

    by_flow: dict[str, list[tuple[SankeyCategory, Decimal]]] = {flow: [] for flow in field_by_flow}
    for category in SankeyCategory.objects.filter(flow__in=field_by_flow):
        field = field_by_flow[category.flow]
        amount = max(Decimal("0"), totals.get(category, {}).get(field, Decimal("0")))
        by_flow[category.flow].append((category, amount))

    return by_flow


def build_sankeymatic_export(  # noqa: PLR0915
    qs: QuerySet[Account], year: int, scheme: str, *, is_budget: bool = False
) -> str:
    """Generate a SankeyMATIC-compatible text file for the given year/type/scheme."""
    from datetime import UTC
    from datetime import datetime

    by_flow = _category_totals(qs, scheme)
    revenue, canton, intercos, commune, dotations = (
        by_flow[SankeyFlow.REVENUE],
        by_flow[SankeyFlow.CANTON],
        by_flow[SankeyFlow.INTERCOMMUNALITY],
        by_flow[SankeyFlow.COMMUNE],
        by_flow[SankeyFlow.DOTATION],
    )

    total_left = sum((v for _c, v in revenue), Decimal("0"))
    total_canton = sum((v for _c, v in canton), Decimal("0"))
    total_intercos = sum((v for _c, v in intercos), Decimal("0"))
    total_commune = sum((v for _c, v in commune), Decimal("0"))
    total_dotations = sum((v for _c, v in dotations), Decimal("0"))
    total_out = total_canton + total_intercos + total_commune + total_dotations
    remainder = total_left - total_out

    def k(val: Decimal) -> int:
        return round(float(val) / 1000)

    def flow_line(src: str, dst: str, val: Decimal) -> str | None:
        n = k(val)
        return f"{src} [{n}] {dst}" if n > 0 else None

    household = SM_LABEL_HOUSEHOLD
    canton_label = SM_LABEL_CANTON
    intercos_label = SM_LABEL_INTERCOMMUNALITIES
    commune_label = SM_LABEL_COMMUNE

    type_label = "Budget" if is_budget else "Comptes"
    now = datetime.now(tz=UTC).strftime("%d/%m/%Y %H:%M:%S")
    lines = [
        f"// SankeyMATIC diagram inputs - Saved: {now}",
        f"// {type_label} {year}",
        "// https://sankeymatic.com/build/",
        "",
        "// === Nodes and Flows ===",
        "",
    ]

    lines.extend(filter(None, (flow_line(c.name, household, v) for c, v in revenue)))
    if remainder < -MIN_VAL:
        lines.append(f"{SM_LABEL_LOSS} [{k(abs(remainder))}] {household}")
    lines.append("")

    lines.extend(
        filter(
            None,
            [
                flow_line(household, canton_label, total_canton),
                flow_line(household, intercos_label, total_intercos),
                flow_line(household, commune_label, total_commune),
            ],
        )
    )
    if remainder > MIN_VAL:
        lines.append(f"{household} [{k(remainder)}] {SM_LABEL_PROFIT}")
    lines.append("")

    lines.extend(filter(None, (flow_line(canton_label, c.name, v) for c, v in canton)))
    lines.append("")
    lines.extend(filter(None, (flow_line(intercos_label, c.name, v) for c, v in intercos)))
    lines.append("")
    lines.extend(filter(None, (flow_line(commune_label, c.name, v) for c, v in commune)))
    lines.append("")
    lines.extend(filter(None, (flow_line(household, c.name, v) for c, v in dotations)))
    lines.append("")

    lines.append("// === Colors ===")
    lines.append("")
    lines.append(f":{household} {COLOR_BUDGET}")
    lines.append(f":{canton_label} {COLOR_CANTON}")
    lines.append(f":{intercos_label} {COLOR_INTERCOS}")
    lines.append(f":{commune_label} {COLOR_COMMUNE}")
    if remainder < -MIN_VAL:
        lines.append(f":{SM_LABEL_LOSS} {COLOR_RESULT}")
    elif remainder > MIN_VAL:
        lines.append(f":{SM_LABEL_PROFIT} {COLOR_PROFIT}")
    seen: set[str] = set()
    for category, value in [*revenue, *canton, *intercos, *commune, *dotations]:
        if k(value) > 0 and category.name not in seen:
            lines.append(f":{category.name} {category.color}")
            seen.add(category.name)
    lines.append("")
    lines.append(SM_SETTINGS)

    return "\n".join(lines)


def build_income_budget_canton_intercos_commune(qs: QuerySet[Account], scheme: str) -> dict:
    """
    Sankey auto-layout with index mapping (no magic numbers).

    Left (revenue categories, data-driven) -> Household ->
      - Canton -> (canton categories, data-driven)
      - Intercommunalités -> (intercommunality categories, data-driven)
      - Commune -> (commune categories, data-driven)
    Dotations flow directly from Household (not a third-party payment).
    """
    by_flow = _category_totals(qs, scheme)
    revenue, canton, intercos, commune, dotations = (
        by_flow[SankeyFlow.REVENUE],
        by_flow[SankeyFlow.CANTON],
        by_flow[SankeyFlow.INTERCOMMUNALITY],
        by_flow[SankeyFlow.COMMUNE],
        by_flow[SankeyFlow.DOTATION],
    )

    total_left = sum((v for _c, v in revenue), Decimal("0"))
    total_canton = sum((v for _c, v in canton), Decimal("0"))
    total_intercos = sum((v for _c, v in intercos), Decimal("0"))
    total_commune = sum((v for _c, v in commune), Decimal("0"))
    total_dotations = sum((v for _c, v in dotations), Decimal("0"))

    idx: dict[str, int] = {}
    labels: list[str] = []
    nodes: list[dict[str, str]] = []
    node_colors: list[str] = []
    links: list[dict[str, float]] = []
    link_colors: list[str] = []

    def node_key(category: SankeyCategory) -> str:
        return f"category-{category.pk}"

    for category, value in revenue:
        _push_node(idx, labels, nodes, node_colors, node_key(category), category.name, value, category.color)

    _push_node(idx, labels, nodes, node_colors, NODE_HOUSEHOLD, LABEL_HOUSEHOLD, total_left, COLOR_BUDGET)
    _push_node(idx, labels, nodes, node_colors, NODE_CANTON, LABEL_CANTON, total_canton, COLOR_CANTON)
    _push_node(
        idx, labels, nodes, node_colors, NODE_INTERCOS, LABEL_INTERCOMMUNALITIES, total_intercos, COLOR_INTERCOS
    )
    _push_node(idx, labels, nodes, node_colors, NODE_COMMUNE, LABEL_COMMUNE, total_commune, COLOR_COMMUNE)

    for category, value in [*canton, *intercos, *commune]:
        _push_node(idx, labels, nodes, node_colors, node_key(category), category.name, value, category.color)

    for category, value in revenue:
        _add_link(idx, links, link_colors, node_key(category), NODE_HOUSEHOLD, value, category.color)

    _add_link(idx, links, link_colors, NODE_HOUSEHOLD, NODE_CANTON, total_canton, COLOR_BUDGET_LINKS)
    _add_link(idx, links, link_colors, NODE_HOUSEHOLD, NODE_INTERCOS, total_intercos, COLOR_BUDGET_LINKS)
    _add_link(idx, links, link_colors, NODE_HOUSEHOLD, NODE_COMMUNE, total_commune, COLOR_BUDGET_LINKS)

    for category, value in canton:
        _add_link(idx, links, link_colors, NODE_CANTON, node_key(category), value, COLOR_CANTON_LINKS)
    for category, value in intercos:
        _add_link(idx, links, link_colors, NODE_INTERCOS, node_key(category), value, COLOR_INTERCOS_LINKS)
    for category, value in commune:
        _add_link(idx, links, link_colors, NODE_COMMUNE, node_key(category), value, COLOR_COMMUNE_LINKS)

    # --- result (cash surplus/deficit after all classified flows, before dotations)
    total_out = total_canton + total_intercos + total_commune + total_dotations
    remainder = total_left - total_out
    if abs(remainder) > MIN_VAL:
        _push_node(idx, labels, nodes, node_colors, NODE_RESULT, LABEL_RESULT_HUB, remainder, COLOR_PROFIT)
        _push_node(idx, labels, nodes, node_colors, KEY_PROFIT, LABEL_PROFIT, remainder, COLOR_PROFIT)
        _add_link(idx, links, link_colors, NODE_HOUSEHOLD, NODE_RESULT, remainder, COLOR_BUDGET_LINKS)
        _add_link(idx, links, link_colors, NODE_RESULT, KEY_PROFIT, remainder, COLOR_PROFIT)

    # Dotations go directly from Household, below the result (not a third-party payment)
    for category, value in dotations:
        _push_node(idx, labels, nodes, node_colors, node_key(category), category.name, value, category.color)
        _add_link(idx, links, link_colors, NODE_HOUSEHOLD, node_key(category), value, COLOR_BUDGET_LINKS)

    return {
        "nodes": nodes,
        "links": links,
        "link_colors": link_colors,
        "node_colors": node_colors,
    }
