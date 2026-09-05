from decimal import Decimal

import pytest

from budgetis.accounting.staged_result import build_staged_result
from budgetis.accounting.staged_result import staged_comparison_flags
from budgetis.accounting.tests.factories import AccountFactory
from budgetis.common.models import ChartScheme


pytestmark = pytest.mark.django_db


class TestBuildStagedResult:
    def test_splits_accounts_into_the_three_tiers(self):
        AccountFactory(year=2027, is_budget=True, nature="3010", charges=Decimal("100.00"), revenues=Decimal("0.00"))
        AccountFactory(year=2027, is_budget=True, nature="4010", charges=Decimal("0.00"), revenues=Decimal("150.00"))
        AccountFactory(year=2027, is_budget=True, nature="3400", charges=Decimal("20.00"), revenues=Decimal("0.00"))
        AccountFactory(year=2027, is_budget=True, nature="4400", charges=Decimal("0.00"), revenues=Decimal("10.00"))
        AccountFactory(year=2027, is_budget=True, nature="3800", charges=Decimal("5.00"), revenues=Decimal("0.00"))
        AccountFactory(year=2027, is_budget=True, nature="4800", charges=Decimal("0.00"), revenues=Decimal("2.00"))

        tiers = build_staged_result([(2027, True)])

        exploitation, financial, extraordinary = tiers
        assert exploitation.col1_charges == Decimal("100.00")
        assert exploitation.col1_revenues == Decimal("150.00")
        assert exploitation.col1_result == Decimal("50.00")

        assert financial.col1_charges == Decimal("20.00")
        assert financial.col1_revenues == Decimal("10.00")
        assert financial.col1_result == Decimal("40.00")  # 50 + (10 - 20)

        assert extraordinary.col1_charges == Decimal("5.00")
        assert extraordinary.col1_revenues == Decimal("2.00")
        assert extraordinary.col1_result == Decimal("37.00")  # 40 + (2 - 5)

    def test_result_is_cumulative_across_tiers(self):
        AccountFactory(year=2027, is_budget=True, nature="3010", charges=Decimal("10.00"), revenues=Decimal("0.00"))
        AccountFactory(year=2027, is_budget=True, nature="4010", charges=Decimal("0.00"), revenues=Decimal("0.00"))

        tiers = build_staged_result([(2027, True)])

        # No financial/extraordinary activity - the final result equals the operating one.
        assert tiers[0].col1_result == tiers[-1].col1_result == Decimal("-10.00")

    def test_each_column_is_its_own_independent_year(self):
        AccountFactory(year=2027, is_budget=True, nature="3010", charges=Decimal("100.00"), revenues=Decimal("0.00"))
        AccountFactory(
            year=2026,
            is_budget=True,
            scheme=ChartScheme.MCH1,
            nature="30",
            charges=Decimal("50.00"),
            revenues=Decimal("0.00"),
        )

        tiers = build_staged_result([(2027, True), (2026, True), (2025, False)])

        assert tiers[0].col1_charges == Decimal("100.00")
        assert tiers[0].col2_charges == Decimal("50.00")
        assert tiers[0].col3_charges == Decimal("0.00")

    def test_works_across_an_mch1_mch2_scheme_change(self):
        """The two-digit nature split is scheme-agnostic - no join by (function, nature, sub_account) is involved."""
        AccountFactory(
            year=2026,
            is_budget=False,
            scheme=ChartScheme.MCH1,
            function="720",
            nature="301",
            charges=Decimal("500.00"),
            revenues=Decimal("0.00"),
        )
        AccountFactory(
            year=2027,
            is_budget=True,
            scheme=ChartScheme.MCH2,
            function="72000",
            nature="3010",
            charges=Decimal("0.00"),
            revenues=Decimal("0.00"),
        )

        tiers = build_staged_result([(2027, True), (2027, True), (2026, False)])

        assert tiers[0].col3_charges == Decimal("500.00")


class TestStagedComparisonFlags:
    def test_budget_view_shows_a_comparison_year_that_simply_has_data(self):
        AccountFactory(year=2026, is_budget=True, scheme=ChartScheme.MCH1)

        flags = staged_comparison_flags(2027, is_budget=True)

        assert flags["show_col2"] is True

    def test_budget_view_hides_a_comparison_year_with_no_data_at_all(self):
        flags = staged_comparison_flags(2027, is_budget=True)

        assert flags["show_col2"] is False
        assert flags["show_col3"] is False

    def test_actuals_view_col2_is_the_budget_of_the_same_year(self):
        AccountFactory(year=2025, is_budget=True, scheme=ChartScheme.MCH1)

        flags = staged_comparison_flags(2025, is_budget=False)

        assert flags["show_col2"] is True
