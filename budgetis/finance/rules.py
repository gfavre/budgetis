from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import TYPE_CHECKING

from .models import SankeyAccountCodeRule
from .models import SankeyCategory
from .models import SankeyLabelRule
from .models import SankeyNatureRangeRule


if TYPE_CHECKING:
    from collections.abc import Iterable

    from budgetis.accounting.models import Account


class SankeyRuleResolver:
    """
    Preloads one scheme's Sankey rules and resolves each account to a
    category. Exact code rules win over label rules, which win over nature
    ranges (checked in ascending priority) - see the rule models' docstrings.
    """

    def __init__(self, scheme: str) -> None:
        self._code_rules = list(SankeyAccountCodeRule.objects.filter(scheme=scheme).select_related("category"))
        self._label_rules = list(SankeyLabelRule.objects.filter(scheme=scheme).select_related("category"))
        self._range_rules = list(SankeyNatureRangeRule.objects.filter(scheme=scheme).select_related("category"))

    def category_for(self, account: Account) -> SankeyCategory | None:
        for code_rule in self._code_rules:
            if (
                code_rule.function == account.function
                and code_rule.nature == account.nature
                and (not code_rule.sub_account or code_rule.sub_account == account.sub_account)
            ):
                return code_rule.category

        label = (account.label or "").lower()
        for label_rule in self._label_rules:
            if label_rule.pattern.lower() in label:
                return label_rule.category

        try:
            nature = int(account.nature)
        except (TypeError, ValueError):
            return None
        for range_rule in self._range_rules:
            if range_rule.matches(nature):
                return range_rule.category

        return None


def aggregate_by_category(accounts: Iterable[Account], scheme: str) -> dict[SankeyCategory, dict[str, Decimal]]:
    """
    Resolves every account to a Sankey category and sums its charges/revenues
    per category. Accounts matching no rule are silently dropped - by design,
    exactly one nature-range rule per scheme should end up as a catch-all
    (like MCH1's contiguous 300-399/400-499 coverage) if a full partition is
    wanted; a gap just means those accounts don't appear in the diagram.
    """
    resolver = SankeyRuleResolver(scheme)
    totals: dict[SankeyCategory, dict[str, Decimal]] = defaultdict(
        lambda: {"charges": Decimal(0), "revenues": Decimal(0)}
    )

    for account in accounts:
        category = resolver.category_for(account)
        if category is None:
            continue
        totals[category]["charges"] += account.charges or Decimal(0)
        totals[category]["revenues"] += account.revenues or Decimal(0)

    return dict(totals)
