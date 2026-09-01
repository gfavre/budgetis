import pytest

from budgetis.accounting.scheme_transition import MappingKind
from budgetis.accounting.scheme_transition import classify_mch2_account
from budgetis.accounting.scheme_transition import comparison_flags
from budgetis.accounting.scheme_transition import first_mch2_year
from budgetis.accounting.tests.factories import AccountCodeMappingFactory
from budgetis.accounting.tests.factories import AvailableYearFactory
from budgetis.common.models import ChartScheme
from budgetis.finance.models import AvailableYear


pytestmark = pytest.mark.django_db

TWO_ORIGINS = 2


class TestClassifyMch2Account:
    def test_no_mapping_is_new(self):
        origin = classify_mch2_account("01100", "3010", "")
        assert origin.kind == MappingKind.NEW
        assert origin.mch1_codes == []

    def test_single_non_splitting_origin_is_one_to_one(self):
        AccountCodeMappingFactory(
            mch1_function="100",
            mch1_nature="301",
            mch1_sub_account="",
            mch2_function="01100",
            mch2_nature="3010",
            mch2_sub_account="",
        )

        origin = classify_mch2_account("01100", "3010", "")

        assert origin.kind == MappingKind.ONE_TO_ONE
        assert origin.mch1_codes == [("100", "301", "")]

    def test_several_non_splitting_origins_is_merge(self):
        AccountCodeMappingFactory(
            mch1_function="110",
            mch1_nature="318",
            mch1_sub_account="",
            mch2_function="96900",
            mch2_nature="3420",
            mch2_sub_account="",
        )
        AccountCodeMappingFactory(
            mch1_function="220",
            mch1_nature="318",
            mch1_sub_account="",
            mch2_function="96900",
            mch2_nature="3420",
            mch2_sub_account="",
        )

        origin = classify_mch2_account("96900", "3420", "")

        assert origin.kind == MappingKind.MERGE
        assert len(origin.mch1_codes) == TWO_ORIGINS

    def test_origin_that_also_maps_elsewhere_is_split(self):
        AccountCodeMappingFactory(
            mch1_function="100",
            mch1_nature="306",
            mch1_sub_account="",
            mch2_function="01100",
            mch2_nature="3049",
            mch2_sub_account="",
        )
        AccountCodeMappingFactory(
            mch1_function="100",
            mch1_nature="306",
            mch1_sub_account="",
            mch2_function="01100",
            mch2_nature="3099",
            mch2_sub_account="",
        )

        origin_a = classify_mch2_account("01100", "3049", "")
        origin_b = classify_mch2_account("01100", "3099", "")

        assert origin_a.kind == MappingKind.SPLIT
        assert origin_b.kind == MappingKind.SPLIT

    def test_merge_and_split_hybrid_is_treated_as_split(self):
        # 110.318 only ever feeds 96900.3420 (would be a merge contributor on
        # its own), but 220.318 *also* splits off to another MCH2 target.
        AccountCodeMappingFactory(
            mch1_function="110",
            mch1_nature="318",
            mch1_sub_account="",
            mch2_function="96900",
            mch2_nature="3420",
            mch2_sub_account="",
        )
        AccountCodeMappingFactory(
            mch1_function="220",
            mch1_nature="318",
            mch1_sub_account="",
            mch2_function="96900",
            mch2_nature="3420",
            mch2_sub_account="",
        )
        AccountCodeMappingFactory(
            mch1_function="220",
            mch1_nature="318",
            mch1_sub_account="",
            mch2_function="97000",
            mch2_nature="3420",
            mch2_sub_account="",
        )

        origin = classify_mch2_account("96900", "3420", "")

        assert origin.kind == MappingKind.SPLIT
        assert len(origin.mch1_codes) == TWO_ORIGINS


class TestFirstMch2Year:
    def test_returns_none_when_no_available_year_uses_mch2(self):
        AvailableYearFactory(year=2026, type=AvailableYear.YearType.BUDGET, scheme=ChartScheme.MCH1)
        assert first_mch2_year(AvailableYear.YearType.BUDGET) is None

    def test_returns_first_year_using_mch2_for_that_type(self):
        AvailableYearFactory(year=2026, type=AvailableYear.YearType.BUDGET, scheme=ChartScheme.MCH1)
        AvailableYearFactory(year=2027, type=AvailableYear.YearType.BUDGET, scheme=ChartScheme.MCH2)
        AvailableYearFactory(year=2028, type=AvailableYear.YearType.BUDGET, scheme=ChartScheme.MCH2)

        assert first_mch2_year(AvailableYear.YearType.BUDGET) == 2027  # noqa: PLR2004

    def test_is_scoped_to_the_given_year_type(self):
        AvailableYearFactory(year=2027, type=AvailableYear.YearType.BUDGET, scheme=ChartScheme.MCH2)

        assert first_mch2_year(AvailableYear.YearType.ACTUAL) is None


class TestComparisonFlags:
    def test_budget_year_drops_both_comparisons_across_the_switch(self):
        AvailableYearFactory(year=2027, type=AvailableYear.YearType.BUDGET, scheme=ChartScheme.MCH2)
        AvailableYearFactory(year=2026, type=AvailableYear.YearType.BUDGET, scheme=ChartScheme.MCH1)
        AvailableYearFactory(year=2025, type=AvailableYear.YearType.ACTUAL, scheme=ChartScheme.MCH1)

        assert comparison_flags(2027, is_budget=True) == {"show_col2": False, "show_col3": False}

    def test_actuals_year_keeps_same_year_budget_but_drops_prev_actuals(self):
        AvailableYearFactory(year=2027, type=AvailableYear.YearType.ACTUAL, scheme=ChartScheme.MCH2)
        AvailableYearFactory(year=2027, type=AvailableYear.YearType.BUDGET, scheme=ChartScheme.MCH2)
        AvailableYearFactory(year=2026, type=AvailableYear.YearType.ACTUAL, scheme=ChartScheme.MCH1)

        assert comparison_flags(2027, is_budget=False) == {"show_col2": True, "show_col3": False}

    def test_actuals_year_within_same_scheme_keeps_both_comparisons(self):
        AvailableYearFactory(year=2026, type=AvailableYear.YearType.ACTUAL, scheme=ChartScheme.MCH1)
        AvailableYearFactory(year=2026, type=AvailableYear.YearType.BUDGET, scheme=ChartScheme.MCH1)
        AvailableYearFactory(year=2025, type=AvailableYear.YearType.ACTUAL, scheme=ChartScheme.MCH1)

        assert comparison_flags(2026, is_budget=False) == {"show_col2": True, "show_col3": True}

    def test_unregistered_current_year_drops_both_comparisons(self):
        assert comparison_flags(2099, is_budget=True) == {"show_col2": False, "show_col3": False}
