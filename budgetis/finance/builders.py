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
    "160.352",
    "310.351",
    "320.352",
    "320.352.1",
    "440.352",
    "540.352",
    "580.352",
    "650.352",
    "660.352",
    "710.352",
    "720.352",
    "810.352",
    "810.352.1",
)


COLOR_IMPOTS = "#2066CF"
COLOR_RANDOM = "#5B8DEF"
COLOR_TAXES = "#F59E0B"
COLOR_RENTALS = "#2BB673"
COLOR_OTHERS = "#6B7280"
COLOR_BUDGET = "#111827"


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
    interests = base.filter(nature__in=INTERESTS_NATURE).aggregate(v=Sum("revenues"))["v"] or Decimal("0")
    others = base.exclude(nature__range=IMPOTS_NATURE_RANGE).exclude(nature__range=TAXES_NATURE_RANGE).exclude(
        nature__in=RENTALS_NATURE + INTERESTS_NATURE
    ).aggregate(v=Sum("revenues"))["v"] or Decimal("0")
    return {
        "impots": impots,
        "randoms": randoms,
        "taxes": taxes,
        "rentals": rentals,
        "interests": interests,
        "others": others,
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
        "social": max(Decimal("0"), social),
        "perequation": max(Decimal("0"), pereq),
        "police": max(Decimal("0"), police),
        "total": max(Decimal("0"), total),
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
        "aisge": max(Decimal("0"), aisge),
        "apec": max(Decimal("0"), apec),
        "transports_region": max(Decimal("0"), trans),
        "autres": max(Decimal("0"), autres),
        "total": max(Decimal("0"), total),
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

    salaires = rng(*WAGES_NATURE_RANGE)
    biens = rng(*GOODS_NATURE_RANGE)
    interets = rng(*INTERESTS_NATURE_RANGE)

    # Aides: base
    q_aides_base = Q(nature__range=AIDS_NATURE_RANGE)

    # Exclure les lignes AISGE en .366 (dans ta liste AISGE : '510.366', '520.366')
    aisge_366_codes = codes_with_nature(AISGE, 366)
    q_excl_aisge_366 = q_from_codes(qs, aisge_366_codes) if aisge_366_codes else Q()

    aides = sum_field(qs, q_aides_base & ~q_excl_aisge_366, "charges")

    total = salaires + biens + interets + aides

    return {
        "salaires": max(Decimal("0"), salaires),
        "biens": max(Decimal("0"), biens),
        "interets": max(Decimal("0"), interets),
        "aides": max(Decimal("0"), aides),
        "total": max(Decimal("0"), total),
    }


def build_income_budget_canton_intercos_commune(qs: QuerySet[Account]) -> dict:  # noqa: PLR0915, PLR0912, C901
    """
    Sankey auto-layout with index mapping (no magic numbers).

    Left (revenues, fixed order) -> Budget ->
      - Canton -> (Sécurité sociale, Péréquation, Police)
      - Intercommunalités -> (AISGE, APEC, Transports région, Associations, Autres intercommunalités)
      - Commune -> (Salaires, Biens & services, Intérêts, Aides & subventions)
    """
    rev = _compute_bucket_sums(qs)
    left = [
        ("impots", _("Impôts"), COLOR_IMPOTS),
        ("randoms", _("Impôts aléatoires"), COLOR_RANDOM),
        ("taxes", _("Taxes"), COLOR_TAXES),
        ("rentals", _("Locations"), COLOR_RENTALS),
        ("interests", _("Intérêts"), COLOR_OTHERS),
        ("others", _("Autres revenus"), COLOR_OTHERS),
    ]
    left_vals = [max(Decimal("0"), rev[k]) for k, _lbl, _c in left]

    canton = compute_canton_breakdown(qs)  # keys: social, perequation, police, total
    inter = compute_intercos(qs)  # keys: aisge, apec, transports_region, autres, total
    commune = compute_commune_breakdown(qs)  # keys: salaires, biens, interets, aides, total

    labels = [lbl for _k, lbl, _c in left] + [
        str(_("Ménage communal")),
        str(_("Canton")),
        str(_("Intercommunalités")),
        str(_("Commune")),
        str(_("Sécurité sociale")),
        str(_("Péréquation")),
        str(_("Police")),
        "AISGE",
        "APEC",
        str(_("Transports région")),
        str(_("Associations")),
        str(_("Autres intercommunalités")),
        str(_("Salaires")),
        str(_("Biens & services")),
        str(_("Intérêts")),
        str(_("Aides & subventions")),
    ]
    idx = {label: i for i, label in enumerate(labels)}

    node_colors = [
        *[c for _k, _l, c in left],
        COLOR_BUDGET,
        "#2F855A",  # Canton
        "#1E3A8A",  # Intercommunalités
        "#CA8A04",  # Commune
        "#86EFAC",
        "#6EE7B7",
        "#34D399",  # Canton leaves
        "#A78BFA",
        "#C4B5FD",
        "#DDD6FE",
        "#E9D5FF",
        "#EDE9FE",  # Intercos leaves (+ Autres)
        "#FDE68A",
        "#FCD34D",
        "#FBBF24",
        "#F59E0B",  # Commune leaves
    ]

    nodes = [{"name": s} for s in labels]
    links, link_colors = [], []

    # Revenus -> Budget
    for i, (_k, _lbl, col) in enumerate(left):
        val = float(left_vals[i])
        if val > 0:
            links.append({"source": i, "target": idx["Ménage communal"], "value": val})
            link_colors.append(col)

    # Budget -> hubs (sum of leaves)
    if canton["total"] > 0:
        links.append({"source": idx["Ménage communal"], "target": idx["Canton"], "value": float(canton["total"])})
        link_colors.append(COLOR_BUDGET)
    if inter["total"] > 0:
        links.append(
            {"source": idx["Ménage communal"], "target": idx["Intercommunalités"], "value": float(inter["total"])}
        )
        link_colors.append(COLOR_BUDGET)
    if commune["total"] > 0:
        links.append({"source": idx["Ménage communal"], "target": idx["Commune"], "value": float(commune["total"])})
        link_colors.append(COLOR_BUDGET)

    # Canton -> leaves
    if canton["social"] > 0:
        links.append({"source": idx["Canton"], "target": idx["Sécurité sociale"], "value": float(canton["social"])})
        link_colors.append("#86EFAC")
    if canton["perequation"] > 0:
        links.append({"source": idx["Canton"], "target": idx["Péréquation"], "value": float(canton["perequation"])})
        link_colors.append("#6EE7B7")
    if canton["police"] > 0:
        links.append({"source": idx["Canton"], "target": idx["Police"], "value": float(canton["police"])})
        link_colors.append("#34D399")

    # Intercommunalités -> leaves (incl. 'Autres intercommunalités')
    if inter["aisge"] > 0:
        links.append({"source": idx["Intercommunalités"], "target": idx["AISGE"], "value": float(inter["aisge"])})
        link_colors.append("#A78BFA")
    if inter["apec"] > 0:
        links.append({"source": idx["Intercommunalités"], "target": idx["APEC"], "value": float(inter["apec"])})
        link_colors.append("#C4B5FD")
    if inter["transports_region"] > 0:
        links.append(
            {
                "source": idx["Intercommunalités"],
                "target": idx["Transports région"],
                "value": float(inter["transports_region"]),
            }
        )
        link_colors.append("#DDD6FE")

    if inter["autres"] > 0:
        links.append(
            {
                "source": idx["Intercommunalités"],
                "target": idx["Autres intercommunalités"],
                "value": float(inter["autres"]),
            }
        )
        link_colors.append("#EDE9FE")

    # Commune -> leaves
    if commune["salaires"] > 0:
        links.append({"source": idx["Commune"], "target": idx["Salaires"], "value": float(commune["salaires"])})
        link_colors.append("#FDE68A")
    if commune["biens"] > 0:
        links.append({"source": idx["Commune"], "target": idx["Biens & services"], "value": float(commune["biens"])})
        link_colors.append("#FCD34D")
    if commune["interets"] > 0:
        links.append({"source": idx["Commune"], "target": idx["Intérêts"], "value": float(commune["interets"])})
        link_colors.append("#FBBF24")
    if commune["aides"] > 0:
        links.append(
            {"source": idx["Commune"], "target": idx["Aides & subventions"], "value": float(commune["aides"])}
        )
        link_colors.append("#F59E0B")

    # Après avoir ajouté tous les liens
    total_in = sum(link["value"] for link in links if link["target"] == idx["Ménage communal"])
    total_out = sum(
        link["value"] for link in links if link["source"] in (idx["Canton"], idx["Intercommunalités"], idx["Commune"])
    )

    reste = total_in - total_out

    if abs(reste) > MIN_VAL:  # seuil pour éviter les artefacts
        labels.append(str(_("Résultat de trésorerie")))
        idx["Résultat de trésorerie"] = len(labels) - 1
        nodes.append({"name": labels[-1]})
        node_colors.append("#374151")  # gris foncé
        links.append(
            {
                "source": idx["Ménage communal"],
                "target": idx["Résultat de trésorerie"],
                "value": to_rounded_float(reste),
            }
        )
        link_colors.append("#374151")

    return {
        "nodes": nodes,
        "links": links,
        "link_colors": link_colors,
        "node_colors": node_colors,
    }
