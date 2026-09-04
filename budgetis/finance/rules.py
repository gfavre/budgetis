from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import TYPE_CHECKING
from typing import TypedDict

from .models import SankeyAccountCodeRule
from .models import SankeyCategory
from .models import SankeyFunctionNatureRule
from .models import SankeyLabelRule
from .models import SankeyNatureRangeRule


if TYPE_CHECKING:
    from collections.abc import Iterable

    from budgetis.accounting.models import Account


class CategoryTotals(TypedDict):
    charges: Decimal
    revenues: Decimal
    accounts: list[Account]


class SankeyRuleResolver:
    """
    Preloads one scheme's Sankey rules and resolves each account to a
    category, most specific first: exact code, then function+nature (a
    family sharing one nature but split by which function pays - see
    SankeyFunctionNatureRule), then label, then nature range (checked in
    ascending priority) - see the rule models' docstrings.
    """

    def __init__(self, scheme: str) -> None:
        self._code_rules = list(SankeyAccountCodeRule.objects.filter(scheme=scheme).select_related("category"))
        self._function_nature_rules = list(
            SankeyFunctionNatureRule.objects.filter(scheme=scheme).select_related("category")
        )
        self._label_rules = list(SankeyLabelRule.objects.filter(scheme=scheme).select_related("category"))
        self._range_rules = list(SankeyNatureRangeRule.objects.filter(scheme=scheme).select_related("category"))

    def category_for(self, account: Account) -> SankeyCategory | None:
        code_category = self._match_code(account)
        if code_category is not None:
            return code_category

        try:
            nature = int(account.nature)
        except (TypeError, ValueError):
            nature = None

        if nature is not None:
            function_nature_category = self._match_function_nature(account.function, nature)
            if function_nature_category is not None:
                return function_nature_category

        label_category = self._match_label(account.label)
        if label_category is not None:
            return label_category

        if nature is not None:
            return self._match_range(nature)

        return None

    def _match_code(self, account: Account) -> SankeyCategory | None:
        for code_rule in self._code_rules:
            if (
                code_rule.function == account.function
                and code_rule.nature == account.nature
                and (not code_rule.sub_account or code_rule.sub_account == account.sub_account)
            ):
                return code_rule.category
        return None

    def _match_function_nature(self, function: str, nature: int) -> SankeyCategory | None:
        for function_nature_rule in self._function_nature_rules:
            if function_nature_rule.matches(function, nature):
                return function_nature_rule.category
        return None

    def _match_label(self, label: str | None) -> SankeyCategory | None:
        lowered = (label or "").lower()
        for label_rule in self._label_rules:
            if label_rule.pattern.lower() in lowered:
                return label_rule.category
        return None

    def _match_range(self, nature: int) -> SankeyCategory | None:
        for range_rule in self._range_rules:
            if range_rule.matches(nature):
                return range_rule.category
        return None


def aggregate_by_category(accounts: Iterable[Account], scheme: str) -> dict[SankeyCategory, CategoryTotals]:
    """
    Resolves every account to a Sankey category, sums its charges/revenues per
    category, and keeps the matched accounts themselves (for the Sankey
    diagram's hover breakdown - see builders._account_breakdown_html).
    Accounts matching no rule are silently dropped - by design, exactly one
    nature-range rule per scheme should end up as a catch-all (like MCH1's
    contiguous 300-399/400-499 coverage) if a full partition is wanted; a gap
    just means those accounts don't appear in the diagram.
    """
    resolver = SankeyRuleResolver(scheme)
    totals: dict[SankeyCategory, CategoryTotals] = defaultdict(
        lambda: {"charges": Decimal(0), "revenues": Decimal(0), "accounts": []}
    )

    for account in accounts:
        category = resolver.category_for(account)
        if category is None:
            continue
        totals[category]["charges"] += account.charges or Decimal(0)
        totals[category]["revenues"] += account.revenues or Decimal(0)
        totals[category]["accounts"].append(account)

    return dict(totals)
