from dataclasses import dataclass
from dataclasses import field
from decimal import Decimal
from typing import Any

from django.utils.translation import gettext_lazy as _

from budgetis.accounting.models import Account


# MCH1 and MCH2 both group natures under the same two-digit codes for the
# financial and extraordinary result (34/44, 38/48) - only the digits after
# that stayed for MCH2's extra precision, so this split works unchanged
# across the scheme transition and lets budget/actuals years be compared
# regardless of which scheme they were recorded under.
FINANCIAL_NATURE_GROUPS = (34, 44)
EXTRAORDINARY_NATURE_GROUPS = (38, 48)


@dataclass
class StagedTier:
    """One step of the "présentation échelonnée": its own charges/revenues, plus the cumulative result so far."""

    label: str
    result_label: str
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


def _bucket_totals(year: int, *, is_budget: bool) -> dict[str, dict]:
    """
    Sums charges/revenues per staged-result bucket for one year, querying
    Account directly rather than going through BudgetLoader/ActualsLoader -
    those loaders match accounts across years by (function, nature,
    sub_account), which never lines up across an MCH1/MCH2 scheme change
    since the codes themselves are structured differently. This report only
    needs a year's own totals per nature group, not a per-account join, so
    it sidesteps that mismatch entirely.
    """
    buckets = {"exploitation": _empty_bucket(), "financial": _empty_bucket(), "extraordinary": _empty_bucket()}
    for nature, charges, revenues in Account.objects.filter(year=year, is_budget=is_budget).values_list(
        "nature", "charges", "revenues"
    ):
        group = _nature_group(nature)
        if group in FINANCIAL_NATURE_GROUPS:
            key = "financial"
        elif group in EXTRAORDINARY_NATURE_GROUPS:
            key = "extraordinary"
        else:
            key = "exploitation"
        buckets[key]["charges"] += charges or Decimal(0)
        buckets[key]["revenues"] += revenues or Decimal(0)
    return buckets


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


def build_staged_result(columns: list[tuple[int, bool]]) -> list[StagedTier]:
    """
    Builds the three tiers of the MCH2 "présentation échelonnée"
    (exploitation, financier, extraordinaire), each building on the
    previous to reach the résultat total de l'exercice.

    `columns` holds up to 3 (year, is_budget) pairs, one per comparison
    column (col1/col2/col3) - a column simply totals to zero if its year
    has no data, matching the behaviour of the rest of the explorer.
    """
    per_col_buckets = [_bucket_totals(year, is_budget=is_budget) for year, is_budget in columns]

    tiers = [
        ("exploitation", _("Operating charges and revenues"), _("Operating result")),
        ("financial", _("Financial charges and revenues"), _("Result before extraordinary items")),
        ("extraordinary", _("Extraordinary charges and revenues"), _("Total result for the year")),
    ]

    result = []
    running_result = [Decimal(0)] * len(columns)
    for bucket_key, label, result_label in tiers:
        tier_kwargs: dict[str, Any] = {"label": label, "result_label": result_label}
        for i, buckets in enumerate(per_col_buckets, start=1):
            charges = buckets[bucket_key]["charges"]
            revenues = buckets[bucket_key]["revenues"]
            running_result[i - 1] += revenues - charges
            tier_kwargs[f"col{i}_charges"] = charges
            tier_kwargs[f"col{i}_revenues"] = revenues
            tier_kwargs[f"col{i}_result"] = running_result[i - 1]
        result.append(StagedTier(**tier_kwargs))

    return result
