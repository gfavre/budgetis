from decimal import Decimal

import pytest

from budgetis.accounting.staged_result import build_staged_result
from budgetis.accounting.staged_result import staged_comparison_flags
from budgetis.accounting.tests.factories import AccountFactory
from budgetis.common.models import ChartScheme


pytestmark = pytest.mark.django_db


def _by_key(lines, key):
    return next(line for line in lines if line.key == key)


class TestBuildStagedResult:
    def test_detail_row_per_nature_group(self):
        AccountFactory(year=2027, is_budget=True, nature="3010", charges=Decimal("100.00"), revenues=Decimal("0.00"))
        AccountFactory(year=2027, is_budget=True, nature="4010", charges=Decimal("0.00"), revenues=Decimal("150.00"))

        lines = build_staged_result([(2027, True)])

        charge_30 = _by_key(lines, "detail-30")
        revenue_40 = _by_key(lines, "detail-40")
        assert charge_30.col1_charges == Decimal("100.00")
        assert revenue_40.col1_revenues == Decimal("150.00")

    def test_operating_charges_and_revenues_subtotals(self):
        AccountFactory(year=2027, is_budget=True, nature="3010", charges=Decimal("100.00"), revenues=Decimal("0.00"))
        AccountFactory(year=2027, is_budget=True, nature="3110", charges=Decimal("20.00"), revenues=Decimal("0.00"))
        AccountFactory(year=2027, is_budget=True, nature="4010", charges=Decimal("0.00"), revenues=Decimal("150.00"))

        lines = build_staged_result([(2027, True)])

        charges_subtotal = _by_key(lines, "operating-charges-subtotal")
        revenues_subtotal = _by_key(lines, "operating-revenues-subtotal")
        assert charges_subtotal.is_subtotal is True
        assert charges_subtotal.col1_charges == Decimal("120.00")
        assert revenues_subtotal.col1_revenues == Decimal("150.00")

    def test_internal_allocations_are_excluded(self):
        # 39/49 "imputations internes" aren't part of Tableau 04-1 - they must
        # not leak into the operating subtotals.
        AccountFactory(year=2027, is_budget=True, nature="3010", charges=Decimal("100.00"), revenues=Decimal("0.00"))
        AccountFactory(year=2027, is_budget=True, nature="3900", charges=Decimal("999.00"), revenues=Decimal("0.00"))

        lines = build_staged_result([(2027, True)])

        assert _by_key(lines, "operating-charges-subtotal").col1_charges == Decimal("100.00")

    def test_splits_accounts_into_the_three_sections(self):
        AccountFactory(year=2027, is_budget=True, nature="3010", charges=Decimal("100.00"), revenues=Decimal("0.00"))
        AccountFactory(year=2027, is_budget=True, nature="4010", charges=Decimal("0.00"), revenues=Decimal("150.00"))
        AccountFactory(year=2027, is_budget=True, nature="3400", charges=Decimal("20.00"), revenues=Decimal("0.00"))
        AccountFactory(year=2027, is_budget=True, nature="4400", charges=Decimal("0.00"), revenues=Decimal("10.00"))
        AccountFactory(year=2027, is_budget=True, nature="3800", charges=Decimal("5.00"), revenues=Decimal("0.00"))
        AccountFactory(year=2027, is_budget=True, nature="4800", charges=Decimal("0.00"), revenues=Decimal("2.00"))

        lines = build_staged_result([(2027, True)])

        assert _by_key(lines, "operating-result").col1_result == Decimal("50.00")
        assert _by_key(lines, "result-before-extraordinary").col1_result == Decimal("40.00")  # 50 + (10-20)
        assert _by_key(lines, "total-result").col1_result == Decimal("37.00")  # 40 + (2-5)

    def test_result_is_cumulative_across_sections(self):
        AccountFactory(year=2027, is_budget=True, nature="3010", charges=Decimal("10.00"), revenues=Decimal("0.00"))
        AccountFactory(year=2027, is_budget=True, nature="4010", charges=Decimal("0.00"), revenues=Decimal("0.00"))

        lines = build_staged_result([(2027, True)])

        # No financial/extraordinary activity - the final result equals the operating one.
        operating = _by_key(lines, "operating-result")
        total = _by_key(lines, "total-result")
        assert operating.col1_result == total.col1_result == Decimal("-10.00")

    def test_result_rows_are_flagged_and_detail_rows_are_not(self):
        lines = build_staged_result([(2027, True)])

        assert _by_key(lines, "operating-result").is_result is True
        assert _by_key(lines, "detail-30").is_result is False
        assert _by_key(lines, "detail-30").is_subtotal is False

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

        lines = build_staged_result([(2027, True), (2026, True), (2025, False)])

        charge_30 = _by_key(lines, "detail-30")
        assert charge_30.col1_charges == Decimal("100.00")
        assert charge_30.col2_charges == Decimal("50.00")
        assert charge_30.col3_charges == Decimal("0.00")

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

        lines = build_staged_result([(2027, True), (2027, True), (2026, False)])

        assert _by_key(lines, "detail-30").col3_charges == Decimal("500.00")


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
