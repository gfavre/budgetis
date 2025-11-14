from __future__ import annotations

from decimal import ROUND_HALF_UP
from decimal import Decimal
from decimal import InvalidOperation
from typing import TYPE_CHECKING

from django.core.exceptions import FieldDoesNotExist
from django.db.models import Q
from django.db.models import QuerySet
from django.db.models import Sum
from django.utils.translation import gettext_lazy as _


if TYPE_CHECKING:
    from collections.abc import Iterable

    from budgetis.accounting.models import Account

# ----- Constants -------------------------------------------------------------
MIN_VAL = 0.5

REVENUE_NATURE_RANGE = (400, 499)
IMPOTS_NATURE_RANGE = (400, 409)
IMPOTS_NATURE_EXCLUDE = (402, 404, 405)
TAXES_NATURE_RANGE = (430, 439)
INTERESTS_NATURE = (422, 424)
RENTALS_NATURE = (423, 425, 427)


WAGES_NATURE_RANGE = (301, 309)
GOODS_NATURE_RANGE = (310, 319)
INTERESTS_NATURE_RANGE = (320, 329)
AIDS_NATURE_RANGE = (360, 369)


SOCIAL_SECURITY = "720.351"
PEREQUATION = "220.352"
POLICE = "600.351"
# 430.351 CHARGES CANTONALES S. HIVERNAL

AISGE = [
    "500.352",
    "510.352",
    "510.366",
    "520.352",
    "520.366",
    "520.352",
    "530.351",
    "530.451",
    "550.352",
    "560.352",
    "570.352",
]
APEC = ("460.352", "460.352.1")
TRANSPORTS_REGION = "180.351"
ASSOCIATIONS = (
    "160.352",  # Région Nyoin - taxes de séjour
    # "310.351",  # Feu bactérien
    "320.352",  # La Colline
    "320.352.1",  # Fondation bois de chênes
    "440.352",  # Centre funéraire de Nyon
    "540.352",  # Orientation Professionneéée  => Evelyne
    "580.352",  # Autres paroisses  => Evelyne
    "650.352",  # SDIS Nyon-Dôle  => Pscal
    "660.352",  # ORPC  => André
    "710.352",  # CSR  => Evelyne
    "720.352",  # ARAS  = Evelyne
    "810.352",  # SAPAN
    "810.352.1",  # Eaudici
)


COLOR_IMPOTS = "#2066CF"
COLOR_RANDOM = "#5B8DEF"
COLOR_TAXES = "#F59E0B"
COLOR_RENTALS = "#2BB673"
COLOR_OTHERS = "#6B7280"

# --- Budget (hub central) ---
COLOR_BUDGET = "#111827"  # gris foncé
COLOR_BUDGET_LINKS = "#9CA3AF"  # gris neutre

# --- Canton ---
COLOR_CANTON = "#15803D"
COLOR_CANTON_LINKS = "#4ADE80"

COLOR_CANTON_SOCIAL = "#86EFAC"
COLOR_CANTON_EQUALIZATION = "#4ADE80"
COLOR_CANTON_POLICE = "#22C55E"

# --- Intercommunalités ---
COLOR_INTERCOS = "#6D28D9"
COLOR_INTERCOS_LINKS = "#C4B5FD"

COLOR_INTERCOS_AISGE = "#A78BFA"
COLOR_INTERCOS_APEC = "#C4B5FD"
COLOR_INTERCOS_TRANSPORTS = "#DDD6FE"
COLOR_INTERCOS_OTHER = "#EDE9FE"

# --- Commune ---
COLOR_COMMUNE = "#D97706"
COLOR_COMMUNE_LINKS = "#FCD34D"

COLOR_COMMUNE_WAGES = "#FDE68A"
COLOR_COMMUNE_GOODS = "#FCD34D"
COLOR_COMMUNE_INTERESTS = "#FBBF24"
COLOR_COMMUNE_AIDS = "#F59E0B"

# --- Résultat ---
COLOR_RESULT = "#374151"

LABEL_HOUSEHOLD = _("Municipal household")
LABEL_CANTON = _("Canton")
LABEL_INTERCOMMUNALITIES = _("Intercommunalities")
LABEL_COMMUNE = _("Commune")

LABEL_SOCIAL = _("Social security")
LABEL_EQUALIZATION = _("Equalization")
LABEL_POLICE = _("Police")

LABEL_AISGE = "AISGE"  # acronym stays the same
LABEL_APEC = "APEC"
LABEL_TRANSPORTS = _("Regional transports")
LABEL_ASSOCIATIONS = _("Associations")
LABEL_INTERCOS_OTHER = _("Other intercommunalities")

LABEL_WAGES = _("Wages")
LABEL_GOODS = _("Goods and services")
LABEL_INTERESTS = _("Interests")
LABEL_AIDS = _("Aids and subsidies")

LABEL_TAXES_GENERAL = _("Taxes (general)")
LABEL_TAXES_RANDOM = _("Random taxes")
LABEL_TAXES_USAGE = _("Levies (usage-based)")
LABEL_RENTALS = _("Rentals")
LABEL_REVENUES_OTHER = _("Other revenues")

LABEL_RESULT = _("Cash result")
LABEL_RESULT_HUB = _("Result")
LABEL_AMORT = _("Amortizations")
LABEL_FUNDS = _("Fund allocations")
LABEL_PROFIT = _("Profit")

# Canton keys
KEY_SOCIAL = "social"
KEY_EQUALIZATION = "equalization"
KEY_POLICE = "police"
KEY_TOTAL = "total"

# Intercommunalities keys
KEY_AISGE = "aisge"
KEY_APEC = "apec"
KEY_TRANSPORTS = "transports_region"
KEY_INTERCOS_OTHER = "other_intercommunalities"

# Commune keys
KEY_WAGES = "wages"
KEY_GOODS = "goods_services"
KEY_INTERESTS = "interests"
KEY_AIDS = "aids"

# Revenue bucket keys (from nature ranges)
KEY_IMPOTS = "taxes_general"
KEY_RANDOMS = "random_taxes"
KEY_LEVIES = "levies_usage"
KEY_RENTALS = "rentals"
KEY_INTERESTS_REV = "interests_revenues"
KEY_OTHERS_REV = "other_revenues"
KEY_RESULT = "result"

KEY_AMORT = "amortizations"
KEY_FUNDS = "fund_allocations"
KEY_PROFIT = "profit"


NODE_HOUSEHOLD = "household"
NODE_CANTON = "canton"
NODE_INTERCOS = "intercommunities"
NODE_COMMUNE = "commune"
NODE_RESULT = "result"


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


def parse_fn_code(code: str) -> tuple[int, int, str | None]:
    """
    Parse a 'function.nature[.subaccount]' code.

    Args:
        code: A string like '720.351' or '460.352.1'.

    Returns:
        Tuple (function, nature, subaccount or None).
    """
    parts = code.split(".")
    if len(parts) <= 1:
        msg = f"Invalid code: {code}"
        raise ValueError(msg)
    function = int(parts[0])
    nature = int(parts[1])
    subaccount = parts[2] if len(parts) >= 3 else None  # noqa: PLR2004
    return function, nature, subaccount


def q_from_code(qs: QuerySet[Account], code: str) -> Q:
    fn, nat, sub = parse_fn_code(code)
    base = Q(function=fn, nature=nat)
    if sub:
        try:
            qs.model._meta.get_field("subaccount")  # noqa: SLF001
            return base & Q(subaccount=sub)
        except FieldDoesNotExist:
            return base
    return base


def q_from_codes(qs: QuerySet[Account], codes: Iterable[str]) -> Q:
    q = Q()
    for c in codes:
        q |= q_from_code(qs, c)
    return q


def sum_field(qs: QuerySet[Account], flt: Q, field: str) -> Decimal:
    return qs.filter(flt).aggregate(v=Sum(field))["v"] or Decimal("0")


def sum_amount_for_codes(
    qs: QuerySet,
    codes: Iterable[str],
    *,
    field: str = "charges",
) -> Decimal:
    """
    Sum a monetary field over entries matching any of the given 'F.N[.S]' codes.

    Args:
        qs: Base queryset already filtered (e.g., year, is_budget=False).
        codes: Iterable of 'F.N[.S]' codes.
        field: Model field to sum ('charges' or 'revenues').

    Returns:
        Decimal sum (0 if nothing matches).
    """
    if not codes:
        return Decimal("0")
    flt = q_from_codes(qs, codes)
    return qs.filter(flt).aggregate(v=Sum(field))["v"] or Decimal("0")


def codes_with_nature(codes: Iterable[str], target_nature: int) -> list[str]:
    out = []
    for c in codes:
        _f, n, _s = parse_fn_code(c)
        if n == target_nature:
            out.append(c)
    return out


def _fmt_chf_short(value: Decimal) -> str:
    """Return CHF amount with K/M suffix."""
    v = value.copy_abs()
    if v >= Decimal("1000000"):
        n = (v / Decimal("1000000")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return f"CHF{n}M"
    n = (v / Decimal("1000")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"CHF{n}K"


def _compute_bucket_sums(qs: QuerySet[Account]) -> dict[str, Decimal]:
    """Sum revenues per bucket (no merge)."""
    base = qs.filter(nature__range=REVENUE_NATURE_RANGE)
    impots = base.filter(nature__range=IMPOTS_NATURE_RANGE).exclude(nature__in=IMPOTS_NATURE_EXCLUDE).aggregate(
        v=Sum("revenues")
    )["v"] or Decimal("0")
    randoms = base.filter(nature__in=IMPOTS_NATURE_EXCLUDE).aggregate(v=Sum("revenues"))["v"] or Decimal("0")
    levies = base.filter(nature__range=TAXES_NATURE_RANGE).aggregate(v=Sum("revenues"))["v"] or Decimal("0")
    rentals = base.filter(nature__in=RENTALS_NATURE).aggregate(v=Sum("revenues"))["v"] or Decimal("0")
    interests = base.filter(nature__in=INTERESTS_NATURE).aggregate(v=Sum("revenues"))["v"] or Decimal("0")
    others = base.exclude(nature__range=IMPOTS_NATURE_RANGE).exclude(nature__range=TAXES_NATURE_RANGE).exclude(
        nature__in=RENTALS_NATURE + INTERESTS_NATURE
    ).aggregate(v=Sum("revenues"))["v"] or Decimal("0")
    return {
        KEY_IMPOTS: impots,
        KEY_RANDOMS: randoms,
        KEY_LEVIES: levies,
        KEY_RENTALS: rentals,
        KEY_INTERESTS_REV: interests,
        KEY_OTHERS_REV: others,
    }


def compute_canton_breakdown(qs: QuerySet) -> dict[str, Decimal]:
    """
    Compute Canton sub-accounts using constants 'F.N[.S]'.
    Uses 'charges' sums.

    Returns:
        Dict with keys: 'social', 'perequation', 'police', 'total'.
    """
    social = sum_amount_for_codes(qs, [SOCIAL_SECURITY], field="charges")
    pereq = sum_amount_for_codes(qs, [PEREQUATION], field="charges")
    police = sum_amount_for_codes(qs, [POLICE], field="charges")
    total = social + pereq + police
    return {
        KEY_SOCIAL: max(Decimal("0"), social),
        KEY_EQUALIZATION: max(Decimal("0"), pereq),
        KEY_POLICE: max(Decimal("0"), police),
        KEY_TOTAL: max(Decimal("0"), total),
    }


def compute_intercos(qs: QuerySet[Account]) -> dict:
    """
    Calcule AISGE, APEC, Transports région et 'autres intercommunalités' (nature 350-359),
    en excluant tout ce qui est déjà classé (Canton + AISGE + APEC + Transports).
    Sums on 'charges'.
    """
    # Blocs identifiés par codes F.N[.S]
    q_aisge = q_from_codes(qs, AISGE)
    q_apec = q_from_codes(qs, APEC)
    q_trans = q_from_codes(qs, [TRANSPORTS_REGION])

    # Les 3 'Canton' sont aussi en nature 351/352 -> à exclure d'intercos.autres
    q_canton = q_from_codes(qs, [SOCIAL_SECURITY, PEREQUATION, POLICE])

    # Base "intercos" = toutes natures 350-359
    q_intercos_base = Q(nature__range=(350, 359))

    # Exclusions déjà traitées
    q_exclude = q_aisge | q_apec | q_trans | q_canton

    # "autres intercos" = base - exclusions
    q_intercos_autres = q_intercos_base & ~q_exclude

    aisge = sum_field(qs, q_aisge, "charges")
    apec = sum_field(qs, q_apec, "charges")
    trans = sum_field(qs, q_trans, "charges")
    autres = sum_field(qs, q_intercos_autres, "charges")

    total = aisge + apec + trans + autres

    return {
        KEY_AISGE: max(Decimal("0"), aisge),
        KEY_APEC: max(Decimal("0"), apec),
        KEY_TRANSPORTS: max(Decimal("0"), trans),
        KEY_INTERCOS_OTHER: max(Decimal("0"), autres),
        KEY_TOTAL: max(Decimal("0"), total),
    }


def compute_commune_breakdown(qs: QuerySet[Account]) -> dict:
    """
    Commune par nature (charges):
      - 301–309  -> salaires
      - 310–319  -> biens
      - 320–329  -> interets
      - 360–369  -> aides  (en excluant les codes AISGE *.366)
    """

    def rng(a: int, b: int) -> Decimal:
        return qs.filter(nature__range=(a, b)).aggregate(v=Sum("charges"))["v"] or Decimal("0")

    wages = rng(*WAGES_NATURE_RANGE)
    goods = rng(*GOODS_NATURE_RANGE)
    interests = rng(*INTERESTS_NATURE_RANGE)

    q_aides_base = Q(nature__range=AIDS_NATURE_RANGE)
    aisge_366_codes = codes_with_nature(AISGE, 366)
    q_excl_aisge_366 = q_from_codes(qs, aisge_366_codes) if aisge_366_codes else Q()
    aids = sum_field(qs, q_aides_base & ~q_excl_aisge_366, "charges")
    total = wages + goods + interests + aids

    return {
        KEY_WAGES: max(Decimal("0"), wages),
        KEY_GOODS: max(Decimal("0"), goods),
        KEY_INTERESTS: max(Decimal("0"), interests),
        KEY_AIDS: max(Decimal("0"), aids),
        KEY_TOTAL: max(Decimal("0"), total),
    }


def _node_label(label: str, val: Decimal) -> str:
    return f"<sub>{label}</sub><br>{_fmt_chf_short(val)}" if val > 0 else label


def _push_node(
    idx: dict[str, int],
    labels: list[str],
    nodes: list[dict[str, str]],
    node_colors: list[str],
    key: str,
    label: str,
    value: Decimal,
    color: str,
) -> None:
    """
    Append a node with a stable key and a formatted label; update color & index map.
    """
    value = Decimal("0") if value is None else Decimal(str(value))
    name = _node_label(str(label), value)
    idx[key] = len(labels)
    labels.append(name)
    nodes.append({"name": name})
    node_colors.append(color)


def _add_link(
    idx: dict[str, int],
    links: list[dict[str, float]],
    link_colors: list[str],
    src_key: str,
    dst_key: str,
    value: Decimal,
    color: str,
) -> None:
    """
    Add a link if value > 0, using stable node keys.
    """
    if value and value > 0:
        links.append({"source": idx[src_key], "target": idx[dst_key], "value": float(value)})
        link_colors.append(color)


def build_income_budget_canton_intercos_commune(qs: QuerySet[Account]) -> dict:  # noqa: PLR0915
    """
    Sankey auto-layout with index mapping (no magic numbers).

    Left (revenues, fixed order) -> Budget ->
      - Canton -> (Sécurité sociale, Péréquation, Police)
      - Intercommunalités -> (AISGE, APEC, Transports région, Associations, Autres intercommunalités)
      - Commune -> (Salaires, Biens & services, Intérêts, Aides & subventions)
    """
    rev = _compute_bucket_sums(qs)
    canton = compute_canton_breakdown(qs)
    inter = compute_intercos(qs)
    commune = compute_commune_breakdown(qs)

    left = [
        (KEY_IMPOTS, LABEL_TAXES_GENERAL, COLOR_IMPOTS),
        (KEY_RANDOMS, LABEL_TAXES_RANDOM, COLOR_RANDOM),
        (KEY_LEVIES, LABEL_TAXES_USAGE, COLOR_TAXES),
        (KEY_RENTALS, LABEL_RENTALS, COLOR_RENTALS),
        (KEY_INTERESTS_REV, LABEL_INTERESTS, COLOR_OTHERS),
        (KEY_OTHERS_REV, LABEL_REVENUES_OTHER, COLOR_OTHERS),
    ]
    left_vals = [max(Decimal("0"), rev[k]) for k, _lbl, _c in left]
    total_left = sum(left_vals)
    total_canton = max(Decimal("0"), canton[KEY_TOTAL])
    total_inter = max(Decimal("0"), inter[KEY_TOTAL])
    total_commune = max(Decimal("0"), commune[KEY_TOTAL])

    # --- build nodes (use stable keys, render labels with values)
    idx: dict[str, int] = {}
    labels: list[str] = []
    nodes: list[dict[str, str]] = []
    node_colors: list[str] = []
    links: list[dict[str, float]] = []
    link_colors: list[str] = []

    # Left revenue nodes
    for i, (k, lbl, col) in enumerate(left):
        _push_node(idx, labels, nodes, node_colors, k, lbl, left_vals[i], col)

    # Hubs
    _push_node(idx, labels, nodes, node_colors, NODE_HOUSEHOLD, LABEL_HOUSEHOLD, total_left, COLOR_BUDGET)
    _push_node(idx, labels, nodes, node_colors, NODE_CANTON, LABEL_CANTON, total_canton, COLOR_CANTON)
    _push_node(idx, labels, nodes, node_colors, NODE_INTERCOS, LABEL_INTERCOMMUNALITIES, total_inter, COLOR_INTERCOS)
    _push_node(idx, labels, nodes, node_colors, NODE_COMMUNE, LABEL_COMMUNE, total_commune, COLOR_COMMUNE)

    # Canton leaves
    _push_node(idx, labels, nodes, node_colors, KEY_SOCIAL, LABEL_SOCIAL, canton[KEY_SOCIAL], COLOR_CANTON_SOCIAL)
    _push_node(
        idx,
        labels,
        nodes,
        node_colors,
        KEY_EQUALIZATION,
        LABEL_EQUALIZATION,
        canton[KEY_EQUALIZATION],
        COLOR_CANTON_EQUALIZATION,
    )
    _push_node(idx, labels, nodes, node_colors, KEY_POLICE, LABEL_POLICE, canton[KEY_POLICE], COLOR_CANTON_POLICE)

    # Intercos leaves
    _push_node(idx, labels, nodes, node_colors, KEY_AISGE, LABEL_AISGE, inter[KEY_AISGE], COLOR_INTERCOS_AISGE)
    _push_node(idx, labels, nodes, node_colors, KEY_APEC, LABEL_APEC, inter[KEY_APEC], COLOR_INTERCOS_APEC)
    _push_node(
        idx,
        labels,
        nodes,
        node_colors,
        KEY_TRANSPORTS,
        LABEL_TRANSPORTS,
        inter[KEY_TRANSPORTS],
        COLOR_INTERCOS_TRANSPORTS,
    )
    _push_node(
        idx,
        labels,
        nodes,
        node_colors,
        KEY_INTERCOS_OTHER,
        LABEL_INTERCOS_OTHER,
        inter[KEY_INTERCOS_OTHER],
        COLOR_INTERCOS_OTHER,
    )

    # Commune leaves
    _push_node(idx, labels, nodes, node_colors, KEY_WAGES, LABEL_WAGES, commune[KEY_WAGES], COLOR_COMMUNE_WAGES)
    _push_node(idx, labels, nodes, node_colors, KEY_GOODS, LABEL_GOODS, commune[KEY_GOODS], COLOR_COMMUNE_GOODS)
    _push_node(
        idx,
        labels,
        nodes,
        node_colors,
        KEY_INTERESTS,
        LABEL_INTERESTS,
        commune[KEY_INTERESTS],
        COLOR_COMMUNE_INTERESTS,
    )
    _push_node(idx, labels, nodes, node_colors, KEY_AIDS, LABEL_AIDS, commune[KEY_AIDS], COLOR_COMMUNE_AIDS)

    for i, (k, _lbl, col) in enumerate(left):
        _add_link(idx, links, link_colors, k, NODE_HOUSEHOLD, left_vals[i], col)

    _add_link(idx, links, link_colors, NODE_HOUSEHOLD, NODE_CANTON, total_canton, COLOR_BUDGET_LINKS)
    _add_link(idx, links, link_colors, NODE_HOUSEHOLD, NODE_INTERCOS, total_inter, COLOR_BUDGET_LINKS)
    _add_link(idx, links, link_colors, NODE_HOUSEHOLD, NODE_COMMUNE, total_commune, COLOR_BUDGET_LINKS)

    _add_link(idx, links, link_colors, NODE_CANTON, KEY_SOCIAL, canton[KEY_SOCIAL], COLOR_CANTON_LINKS)
    _add_link(idx, links, link_colors, NODE_CANTON, KEY_EQUALIZATION, canton[KEY_EQUALIZATION], COLOR_CANTON_LINKS)
    _add_link(idx, links, link_colors, NODE_CANTON, KEY_POLICE, canton[KEY_POLICE], COLOR_CANTON_LINKS)

    _add_link(idx, links, link_colors, NODE_INTERCOS, KEY_AISGE, inter[KEY_AISGE], COLOR_INTERCOS_LINKS)
    _add_link(idx, links, link_colors, NODE_INTERCOS, KEY_APEC, inter[KEY_APEC], COLOR_INTERCOS_LINKS)
    _add_link(idx, links, link_colors, NODE_INTERCOS, KEY_TRANSPORTS, inter[KEY_TRANSPORTS], COLOR_INTERCOS_LINKS)
    _add_link(
        idx, links, link_colors, NODE_INTERCOS, KEY_INTERCOS_OTHER, inter[KEY_INTERCOS_OTHER], COLOR_INTERCOS_LINKS
    )

    _add_link(idx, links, link_colors, NODE_COMMUNE, KEY_WAGES, commune[KEY_WAGES], COLOR_COMMUNE_LINKS)
    _add_link(idx, links, link_colors, NODE_COMMUNE, KEY_GOODS, commune[KEY_GOODS], COLOR_COMMUNE_LINKS)
    _add_link(idx, links, link_colors, NODE_COMMUNE, KEY_INTERESTS, commune[KEY_INTERESTS], COLOR_COMMUNE_LINKS)
    _add_link(idx, links, link_colors, NODE_COMMUNE, KEY_AIDS, commune[KEY_AIDS], COLOR_COMMUNE_LINKS)

    # --- result
    total_out = total_canton + total_inter + total_commune
    remainder = total_left - total_out
    if abs(remainder) > MIN_VAL:
        amort_val = Decimal(0)  # TODO: calcul réel
        funds_val = Decimal(0)  # TODO: calcul réel
        profit_val = remainder - amort_val - funds_val

        # Hub résultat
        _push_node(idx, labels, nodes, node_colors, NODE_RESULT, LABEL_RESULT_HUB, remainder, COLOR_RESULT)

        # Leaves
        _push_node(idx, labels, nodes, node_colors, KEY_AMORT, LABEL_AMORT, amort_val, COLOR_RESULT)
        _push_node(idx, labels, nodes, node_colors, KEY_FUNDS, LABEL_FUNDS, funds_val, COLOR_RESULT)
        _push_node(idx, labels, nodes, node_colors, KEY_PROFIT, LABEL_PROFIT, profit_val, COLOR_RESULT)

        # Liens
        _add_link(idx, links, link_colors, NODE_HOUSEHOLD, NODE_RESULT, remainder, COLOR_BUDGET_LINKS)
        _add_link(idx, links, link_colors, NODE_RESULT, KEY_AMORT, amort_val, COLOR_RESULT)
        _add_link(idx, links, link_colors, NODE_RESULT, KEY_FUNDS, funds_val, COLOR_RESULT)
        _add_link(idx, links, link_colors, NODE_RESULT, KEY_PROFIT, profit_val, COLOR_RESULT)

    return {
        "nodes": nodes,  # [{"name": "Label<br>CHF…"}, ...]
        "links": links,  # [{"source": i, "target": j, "value": ...}, ...]
        "link_colors": link_colors,
        "node_colors": node_colors,
    }
