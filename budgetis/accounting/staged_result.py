"""
Compte de résultats - présentation échelonnée (MCH2).

Structure, nature-group boundaries and labels are taken verbatim from the
official handbook: SRS-CSPCP, "Manuel MCH2" 2e édition (mars 2022),
Recommandation 04 "Compte de résultats", §12 and Tableau 04-1. Full citation,
the reproduced table, and the "impôts aléatoires" question this settled:
see docs/staged-result.md at the repo root.
"""

from dataclasses import dataclass
from dataclasses import field
from decimal import Decimal
from typing import Any

from django.utils.translation import gettext_lazy as _

from budgetis.accounting.models import Account


# Tableau 04-1's own grouping, reproduced exactly - two-digit nature groups,
# stable across the MCH1/MCH2 scheme change (only the digit *count* changed,
# see docs/staged-result.md), so this split works unchanged whichever scheme
# a given column's year was recorded under. 39/49 "imputations internes" are
# deliberately absent from the table (and so from here): they net out between
# charges and revenues and aren't part of the staged presentation.
EXPLOITATION_CHARGE_GROUPS = (30, 31, 33, 35, 36, 37)
EXPLOITATION_REVENUE_GROUPS = (40, 41, 42, 43, 45, 46, 47)
FINANCIAL_CHARGE_GROUP = 34
FINANCIAL_REVENUE_GROUP = 44
EXTRAORDINARY_CHARGE_GROUP = 38
EXTRAORDINARY_REVENUE_GROUP = 48

# Labels straight off Tableau 04-1 - kept local to this module rather than
# reusing accounting.nature.NATURE_GROUPS, which is a looser MCH1-era
# approximation (it's missing 37/47 entirely and labels 44 differently).
GROUP_LABELS: dict[int, Any] = {
    30: _("Personnel charges"),
    31: _("Goods, services and other operating charges"),
    33: _("Depreciation of administrative assets"),
    35: _("Allocations to funds and special financing"),
    36: _("Transfer charges"),
    37: _("Subsidies passed on"),
    40: _("Tax revenues"),
    41: _("Licenses and concessions"),
    42: _("Fees"),
    43: _("Miscellaneous revenues"),
    45: _("Withdrawals from funds and special financing"),
    46: _("Transfer revenues"),
    47: _("Subsidies to be passed on"),
    34: _("Financial charges"),
    44: _("Financial revenues"),
    38: _("Extraordinary charges"),
    48: _("Extraordinary revenues"),
}


@dataclass
class StagedLine:
    """
    One row of the "présentation échelonnée" table: either a detail row (one
    nature group), a subtotal row (`is_subtotal`, e.g. "Total operating
    charges"), or a result row (`is_result`, e.g. "Résultat d'exploitation") -
    the template renders each kind differently. A result row carries its
    cumulative running total in `col*_result` instead of charges/revenues.
    `key` is a stable, untranslated identifier (e.g. "detail-30",
    "operating-result") for code/tests to look a row up by - `label` is
    user-facing and translated, so it shouldn't be matched against.
    """

    label: str
    key: str = ""
    is_subtotal: bool = False
    is_result: bool = False
    col1_charges: Decimal = field(default_factory=Decimal)
    col1_revenues: Decimal = field(default_factory=Decimal)
    col2_charges: Decimal = field(default_factory=Decimal)
    col2_revenues: Decimal = field(default_factory=Decimal)
    col3_charges: Decimal = field(default_factory=Decimal)
    col3_revenues: Decimal = field(default_factory=Decimal)
    col1_result: Decimal = field(default_factory=Decimal)
    col2_result: Decimal = field(default_factory=Decimal)
    col3_result: Decimal = field(default_factory=Decimal)


def _nature_group(nature: str) -> int | None:
    try:
        return int(str(nature)[:2])
    except (TypeError, ValueError):
        return None


def _empty_bucket() -> dict:
    return {"charges": Decimal(0), "revenues": Decimal(0)}


def _nature_group_totals(year: int, *, is_budget: bool) -> dict[int, dict]:
    """
    Sums charges/revenues per two-digit nature group for one year, querying
    Account directly rather than going through BudgetLoader/ActualsLoader -
    those loaders match accounts across years by (function, nature,
    sub_account), which never lines up across an MCH1/MCH2 scheme change
    since the codes themselves are structured differently. This report only
    needs a year's own totals per nature group, not a per-account join, so
    it sidesteps that mismatch entirely.
    """
    totals: dict[int, dict] = {}
    for nature, charges, revenues in Account.objects.filter(year=year, is_budget=is_budget).values_list(
        "nature", "charges", "revenues"
    ):
        group = _nature_group(nature)
        if group is None:
            continue
        bucket = totals.setdefault(group, _empty_bucket())
        bucket["charges"] += charges or Decimal(0)
        bucket["revenues"] += revenues or Decimal(0)
    return totals


def _group_amount(totals: dict, code: int, side: str) -> Decimal:
    return totals.get(code, _empty_bucket())[side]


def staged_comparison_flags(year: int, *, is_budget: bool) -> dict[str, bool]:
    """
    Unlike the detailed explorers (see accounting.scheme_transition.comparison_flags),
    which hide a comparison year entirely across an MCH1/MCH2 scheme change
    because per-account codes don't line up, the staged result only
    aggregates by two-digit nature group - a classification that stayed
    stable across that transition - so a comparison column is shown
    whenever that year simply has data, regardless of which scheme it was
    recorded under.
    """
    if is_budget:
        col2_year, col2_is_budget = year - 1, True
        col3_year, col3_is_budget = year - 2, False
    else:
        col2_year, col2_is_budget = year, True
        col3_year, col3_is_budget = year - 1, False
    show_col2 = Account.objects.filter(year=col2_year, is_budget=col2_is_budget).exists()
    show_col3 = Account.objects.filter(year=col3_year, is_budget=col3_is_budget).exists()
    return {"show_col2": show_col2, "show_col3": show_col3}


def build_staged_result(columns: list[tuple[int, bool]]) -> list[StagedLine]:
    """
    Builds the full "présentation échelonnée" line by line, straight off
    Tableau 04-1 (see this module's docstring): a detail row per nature
    group, a subtotal row for each side of the operating section, and a
    result row after each of the three sections (exploitation, financier,
    extraordinaire), each result row's total carrying forward into the next.

    `columns` holds up to 3 (year, is_budget) pairs, one per comparison
    column (col1/col2/col3) - a column simply totals to zero if its year
    has no data, matching the behaviour of the rest of the explorer.
    """
    per_col_totals = [_nature_group_totals(year, is_budget=is_budget) for year, is_budget in columns]
    n = len(columns)

    lines: list[StagedLine] = []
    running_result = [Decimal(0)] * n

    def detail_row(code: int, side: str) -> None:
        kwargs: dict[str, Any] = {"label": f"{code} - {GROUP_LABELS[code]}", "key": f"detail-{code}"}
        for i, totals in enumerate(per_col_totals, start=1):
            kwargs[f"col{i}_{side}"] = _group_amount(totals, code, side)
        lines.append(StagedLine(**kwargs))

    def subtotal_row(key: str, label: Any, codes: tuple[int, ...], side: str) -> list[Decimal]:
        amounts = []
        kwargs: dict[str, Any] = {"label": label, "key": key, "is_subtotal": True}
        for i, totals in enumerate(per_col_totals, start=1):
            amount = sum((_group_amount(totals, code, side) for code in codes), Decimal(0))
            kwargs[f"col{i}_{side}"] = amount
            amounts.append(amount)
        lines.append(StagedLine(**kwargs))
        return amounts

    def result_row(key: str, label: Any, col_deltas: list[Decimal]) -> None:
        kwargs: dict[str, Any] = {"label": label, "key": key, "is_result": True}
        for i, delta in enumerate(col_deltas, start=1):
            running_result[i - 1] += delta
            kwargs[f"col{i}_result"] = running_result[i - 1]
        lines.append(StagedLine(**kwargs))

    for code in EXPLOITATION_CHARGE_GROUPS:
        detail_row(code, "charges")
    charges_subtotal = subtotal_row(
        "operating-charges-subtotal", _("Total operating charges"), EXPLOITATION_CHARGE_GROUPS, "charges"
    )
    for code in EXPLOITATION_REVENUE_GROUPS:
        detail_row(code, "revenues")
    revenues_subtotal = subtotal_row(
        "operating-revenues-subtotal", _("Total operating revenues"), EXPLOITATION_REVENUE_GROUPS, "revenues"
    )
    exploitation_deltas = [rev - chg for rev, chg in zip(revenues_subtotal, charges_subtotal, strict=True)]
    result_row("operating-result", _("Operating result"), exploitation_deltas)

    detail_row(FINANCIAL_CHARGE_GROUP, "charges")
    detail_row(FINANCIAL_REVENUE_GROUP, "revenues")
    financial_deltas = [
        _group_amount(totals, FINANCIAL_REVENUE_GROUP, "revenues")
        - _group_amount(totals, FINANCIAL_CHARGE_GROUP, "charges")
        for totals in per_col_totals
    ]
    result_row("result-before-extraordinary", _("Result before extraordinary items"), financial_deltas)

    detail_row(EXTRAORDINARY_CHARGE_GROUP, "charges")
    detail_row(EXTRAORDINARY_REVENUE_GROUP, "revenues")
    extraordinary_deltas = [
        _group_amount(totals, EXTRAORDINARY_REVENUE_GROUP, "revenues")
        - _group_amount(totals, EXTRAORDINARY_CHARGE_GROUP, "charges")
        for totals in per_col_totals
    ]
    result_row("total-result", _("Total result for the year"), extraordinary_deltas)

    return lines
