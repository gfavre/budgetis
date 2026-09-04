from decimal import Decimal

import pytest

from budgetis.accounting.tests.factories import AccountFactory
from budgetis.common.models import ChartScheme
from budgetis.finance.models import SankeyFlow
from budgetis.finance.rules import SankeyRuleResolver
from budgetis.finance.rules import aggregate_by_category
from budgetis.finance.tests.factories import SankeyAccountCodeRuleFactory
from budgetis.finance.tests.factories import SankeyCategoryFactory
from budgetis.finance.tests.factories import SankeyFunctionNatureRuleFactory
from budgetis.finance.tests.factories import SankeyLabelRuleFactory
from budgetis.finance.tests.factories import SankeyNatureRangeRuleFactory


pytestmark = pytest.mark.django_db

# Test-only codes chosen to fall outside every range/code seeded by the finance
# migrations (MCH1 up to nature 499, MCH2 up to nature 4699), so tests never
# collide with the production data loaded into the test database.
TEST_FUNCTION = "900"
TEST_NATURE = "9000"


class TestSankeyRuleResolver:
    def test_exact_code_rule_beats_label_and_range_rules(self):
        code_category = SankeyCategoryFactory()
        label_category = SankeyCategoryFactory()
        range_category = SankeyCategoryFactory()
        SankeyAccountCodeRuleFactory(
            scheme=ChartScheme.MCH1, function=TEST_FUNCTION, nature=TEST_NATURE, category=code_category
        )
        SankeyLabelRuleFactory(scheme=ChartScheme.MCH1, pattern="quelconque", category=label_category)
        SankeyNatureRangeRuleFactory(
            scheme=ChartScheme.MCH1, nature_start=9000, nature_end=9009, category=range_category
        )
        account = AccountFactory.build(
            function=TEST_FUNCTION, nature=TEST_NATURE, sub_account="", label="Autre chose quelconque"
        )

        resolver = SankeyRuleResolver(ChartScheme.MCH1)

        assert resolver.category_for(account) == code_category

    def test_exact_code_rule_beats_function_nature_rule(self):
        code_category = SankeyCategoryFactory()
        function_nature_category = SankeyCategoryFactory()
        SankeyAccountCodeRuleFactory(scheme=ChartScheme.MCH2, function="90000", nature="9000", category=code_category)
        SankeyFunctionNatureRuleFactory(
            scheme=ChartScheme.MCH2,
            function_prefix="900",
            nature_start=9000,
            nature_end=9000,
            category=function_nature_category,
        )
        account = AccountFactory.build(function="90000", nature="9000", sub_account="")

        resolver = SankeyRuleResolver(ChartScheme.MCH2)

        assert resolver.category_for(account) == code_category

    def test_function_nature_rule_beats_label_and_range_rules(self):
        function_nature_category = SankeyCategoryFactory()
        label_category = SankeyCategoryFactory()
        range_category = SankeyCategoryFactory()
        SankeyFunctionNatureRuleFactory(
            scheme=ChartScheme.MCH2,
            function_prefix="900",
            nature_start=9000,
            nature_end=9000,
            category=function_nature_category,
        )
        SankeyLabelRuleFactory(scheme=ChartScheme.MCH2, pattern="quelconque", category=label_category)
        SankeyNatureRangeRuleFactory(
            scheme=ChartScheme.MCH2, nature_start=9000, nature_end=9099, category=range_category
        )
        account = AccountFactory.build(function="90000", nature="9000", label="Autre chose quelconque")

        resolver = SankeyRuleResolver(ChartScheme.MCH2)

        assert resolver.category_for(account) == function_nature_category

    def test_function_nature_rule_requires_matching_function_prefix(self):
        function_nature_category = SankeyCategoryFactory()
        range_category = SankeyCategoryFactory()
        SankeyFunctionNatureRuleFactory(
            scheme=ChartScheme.MCH2,
            function_prefix="900",
            nature_start=9000,
            nature_end=9000,
            category=function_nature_category,
        )
        SankeyNatureRangeRuleFactory(
            scheme=ChartScheme.MCH2, nature_start=9000, nature_end=9099, category=range_category
        )
        account = AccountFactory.build(function="91000", nature="9000")

        resolver = SankeyRuleResolver(ChartScheme.MCH2)

        assert resolver.category_for(account) == range_category

    def test_label_rule_beats_range_rule(self):
        label_category = SankeyCategoryFactory()
        range_category = SankeyCategoryFactory()
        SankeyLabelRuleFactory(scheme=ChartScheme.MCH2, pattern="ZZZTEST", category=label_category)
        SankeyNatureRangeRuleFactory(
            scheme=ChartScheme.MCH2, nature_start=9000, nature_end=9099, category=range_category
        )
        account = AccountFactory.build(function=TEST_FUNCTION, nature="9050", label="Cotisation ZZZTEST 2027")

        resolver = SankeyRuleResolver(ChartScheme.MCH2)

        assert resolver.category_for(account) == label_category

    def test_blank_sub_account_matches_any_sub_account(self):
        category = SankeyCategoryFactory()
        SankeyAccountCodeRuleFactory(
            scheme=ChartScheme.MCH1, function=TEST_FUNCTION, nature=TEST_NATURE, sub_account="", category=category
        )
        account = AccountFactory.build(function=TEST_FUNCTION, nature=TEST_NATURE, sub_account="1")

        resolver = SankeyRuleResolver(ChartScheme.MCH1)

        assert resolver.category_for(account) == category

    def test_nature_range_priority_is_ascending_first_match_wins(self):
        narrow = SankeyCategoryFactory()
        broad = SankeyCategoryFactory()
        SankeyNatureRangeRuleFactory(
            scheme=ChartScheme.MCH1, nature_start=9002, nature_end=9002, priority=10, category=narrow
        )
        SankeyNatureRangeRuleFactory(
            scheme=ChartScheme.MCH1, nature_start=9000, nature_end=9009, priority=50, category=broad
        )
        account = AccountFactory.build(function=TEST_FUNCTION, nature="9002")

        resolver = SankeyRuleResolver(ChartScheme.MCH1)

        assert resolver.category_for(account) == narrow

    def test_no_matching_rule_returns_none(self):
        account = AccountFactory.build(function=TEST_FUNCTION, nature="9999")

        resolver = SankeyRuleResolver(ChartScheme.MCH1)

        assert resolver.category_for(account) is None

    def test_non_numeric_nature_returns_none(self):
        account = AccountFactory.build(function=TEST_FUNCTION, nature="")

        resolver = SankeyRuleResolver(ChartScheme.MCH1)

        assert resolver.category_for(account) is None

    def test_only_rules_for_the_requested_scheme_are_considered(self):
        mch2_category = SankeyCategoryFactory()
        SankeyNatureRangeRuleFactory(
            scheme=ChartScheme.MCH2, nature_start=9000, nature_end=9009, category=mch2_category
        )
        account = AccountFactory.build(function=TEST_FUNCTION, nature="9005")

        resolver = SankeyRuleResolver(ChartScheme.MCH1)

        assert resolver.category_for(account) is None


class TestAggregateByCategory:
    def test_sums_charges_and_revenues_per_category(self):
        category = SankeyCategoryFactory(flow=SankeyFlow.COMMUNE)
        SankeyNatureRangeRuleFactory(scheme=ChartScheme.MCH1, nature_start=9000, nature_end=9009, category=category)
        accounts = [
            AccountFactory.build(
                function=TEST_FUNCTION, nature="9001", charges=Decimal("1000.00"), revenues=Decimal("0.00")
            ),
            AccountFactory.build(
                function=TEST_FUNCTION, nature="9002", charges=Decimal("500.00"), revenues=Decimal("0.00")
            ),
        ]

        totals = aggregate_by_category(accounts, ChartScheme.MCH1)
        vals = next(v for k, v in totals.items() if k == category)

        assert vals["charges"] == Decimal("1500.00")
        assert vals["revenues"] == Decimal("0.00")

    def test_unmatched_accounts_are_dropped(self):
        accounts = [AccountFactory.build(function=TEST_FUNCTION, nature="9999", charges=Decimal("1000.00"))]

        totals = aggregate_by_category(accounts, ChartScheme.MCH1)

        assert totals == {}
