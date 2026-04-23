from decimal import Decimal

from budgetis.accounting.templatetags.money import format_money
from budgetis.accounting.templatetags.money import format_money_abs
from budgetis.accounting.templatetags.money import money_cell
from budgetis.accounting.templatetags.money import percent_diff
from budgetis.accounting.templatetags.money import percent_diff_display


THIN_SPACE = "\u202f"
PERCENT_INCREASE = 10.0
PERCENT_DECREASE = -10.0


class TestFormatMoney:
    def test_none_returns_empty_string(self):
        assert format_money(None) == ""

    def test_integer_with_thousand_separator(self):
        assert format_money(1000) == f"1{THIN_SPACE}000"

    def test_large_number_groups_thousands(self):
        assert format_money(1234567) == f"1{THIN_SPACE}234{THIN_SPACE}567"

    def test_zero_cents_omitted(self):
        assert format_money(Decimal("1000.00")) == f"1{THIN_SPACE}000"

    def test_non_zero_cents_kept(self):
        assert format_money(Decimal("1000.50")) == f"1{THIN_SPACE}000.50"

    def test_negative_value(self):
        assert format_money(Decimal("-500.00")) == "-500"

    def test_zero(self):
        assert format_money(0) == "0"


class TestFormatMoneyAbs:
    def test_negative_becomes_positive(self):
        assert format_money_abs(Decimal("-500.00")) == "500"

    def test_positive_unchanged(self):
        assert format_money_abs(Decimal("500.00")) == "500"

    def test_none_returns_empty(self):
        assert format_money_abs(None) == ""


class TestMoneyCell:
    def test_nonzero_value_formats_amount(self):
        assert money_cell(Decimal("500.00"), Decimal("0")) == "500"

    def test_zero_value_with_nonzero_other_returns_blank(self):
        assert money_cell(Decimal("0"), Decimal("500")) == ""

    def test_both_zero_returns_dash(self):
        assert money_cell(Decimal("0"), Decimal("0")) == "-"

    def test_none_value_with_nonzero_other_returns_blank(self):
        assert money_cell(None, Decimal("100")) == ""

    def test_both_none_returns_dash(self):
        assert money_cell(None, None) == "-"


class TestPercentDiff:
    def test_increase_returns_positive(self):
        assert percent_diff(110, 100) == PERCENT_INCREASE

    def test_decrease_returns_negative(self):
        assert percent_diff(90, 100) == PERCENT_DECREASE

    def test_zero_budget_returns_empty_string(self):
        assert percent_diff(100, 0) == ""

    def test_none_actual_returns_empty_string(self):
        assert percent_diff(None, 100) == ""

    def test_none_budget_returns_empty_string(self):
        assert percent_diff(100, None) == ""

    def test_equal_values_returns_zero(self):
        assert percent_diff(100, 100) == 0.0


class TestPercentDiffDisplay:
    def test_positive_charge_delta_is_danger(self):
        result = percent_diff_display(PERCENT_INCREASE)
        assert "text-danger" in result
        assert "+10%" in result

    def test_negative_charge_delta_is_success(self):
        result = percent_diff_display(PERCENT_DECREASE)
        assert "text-success" in result

    def test_zero_delta_is_muted(self):
        result = percent_diff_display(0.0)
        assert "text-muted" in result

    def test_positive_revenue_delta_is_success(self):
        result = percent_diff_display(PERCENT_INCREASE, is_revenue=True)
        assert "text-success" in result

    def test_negative_revenue_delta_is_danger(self):
        result = percent_diff_display(PERCENT_DECREASE, is_revenue=True)
        assert "text-danger" in result

    def test_empty_string_returns_empty(self):
        assert percent_diff_display("") == ""

    def test_none_returns_empty(self):
        assert percent_diff_display(None) == ""

    def test_result_is_html_with_small_tag(self):
        result = percent_diff_display(5.0)
        assert result.startswith("<small")
        assert "</small>" in result
