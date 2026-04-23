from collections import OrderedDict
from decimal import Decimal

import pytest

from budgetis.accounting.groupers import _nature_group
from budgetis.accounting.groupers import build_grouped
from budgetis.accounting.groupers import build_nature_grouped
from budgetis.accounting.groupers import build_summary
from budgetis.accounting.tests.factories import AccountFactory
from budgetis.accounting.tests.factories import AccountGroupFactory
from budgetis.accounting.tests.factories import MetaGroupFactory
from budgetis.accounting.tests.factories import SuperGroupFactory
from budgetis.accounting.views.data import AccountRow


pytestmark = pytest.mark.django_db

NATURE_30 = 30
NATURE_35 = 35
TWO_ACCOUNTS = 2
TWO_ROWS = 2


def _row(account, **col_kwargs) -> AccountRow:
    return AccountRow(account=account, **col_kwargs)


class TestBuildGrouped:
    def test_empty_rows_returns_empty_ordered_dict(self):
        assert build_grouped([], 2024) == OrderedDict()

    def test_accumulates_totals_at_all_hierarchy_levels(self):
        mg = MetaGroupFactory()
        sg = SuperGroupFactory(metagroup=mg)
        ag = AccountGroupFactory(supergroup=sg)
        acc = AccountFactory(group=ag)
        row = _row(acc, col1_charges=Decimal("500"), col1_revenues=Decimal("200"))

        result = build_grouped([row], 2024)

        mg_data = result[mg.code]
        sg_data = mg_data["supergroups"][sg.code]
        ag_data = sg_data["groups"][ag.code]
        assert mg_data["col1_charges"] == Decimal("500")
        assert sg_data["col1_charges"] == Decimal("500")
        assert ag_data["col1_charges"] == Decimal("500")
        assert ag_data["col1_revenues"] == Decimal("200")

    def test_two_rows_in_same_group_accumulate(self):
        mg = MetaGroupFactory()
        sg = SuperGroupFactory(metagroup=mg)
        ag = AccountGroupFactory(supergroup=sg)
        acc1 = AccountFactory(group=ag)
        acc2 = AccountFactory(group=ag)
        row1 = _row(acc1, col1_charges=Decimal("300"))
        row2 = _row(acc2, col1_charges=Decimal("700"))

        result = build_grouped([row1, row2], 2024)
        ag_data = result[mg.code]["supergroups"][sg.code]["groups"][ag.code]
        assert ag_data["col1_charges"] == Decimal("1000")
        assert len(ag_data["accounts"]) == TWO_ACCOUNTS

    def test_row_without_group_is_skipped(self):
        acc = AccountFactory(group=None)
        row = _row(acc, col1_charges=Decimal("999"))
        assert build_grouped([row], 2024) == OrderedDict()

    def test_accounts_sorted_by_function_within_group(self):
        mg = MetaGroupFactory()
        sg = SuperGroupFactory(metagroup=mg)
        ag = AccountGroupFactory(supergroup=sg)
        acc_b = AccountFactory(group=ag, function="720", nature="351")
        acc_a = AccountFactory(group=ag, function="460", nature="351")
        row_b = _row(acc_b, col1_charges=Decimal("100"))
        row_a = _row(acc_a, col1_charges=Decimal("200"))

        result = build_grouped([row_b, row_a], 2024)
        accounts = result[mg.code]["supergroups"][sg.code]["groups"][ag.code]["accounts"]
        functions = [r.account.function for r in accounts]
        assert functions == sorted(functions)


class TestBuildSummary:
    def _grouped(self, **cols) -> OrderedDict:
        defaults = {
            "col1_charges": Decimal("0"),
            "col1_revenues": Decimal("0"),
            "col2_charges": Decimal("0"),
            "col2_revenues": Decimal("0"),
            "col3_charges": Decimal("0"),
            "col3_revenues": Decimal("0"),
        }
        defaults.update(cols)
        return OrderedDict([(1, {"label": "A", **defaults})])

    def test_totals_sum_across_entries(self):
        grouped = OrderedDict(
            [
                (
                    1,
                    {
                        "label": "A",
                        "col1_charges": Decimal("500"),
                        "col1_revenues": Decimal("0"),
                        "col2_charges": Decimal("0"),
                        "col2_revenues": Decimal("0"),
                        "col3_charges": Decimal("0"),
                        "col3_revenues": Decimal("0"),
                    },
                ),
                (
                    2,
                    {
                        "label": "B",
                        "col1_charges": Decimal("300"),
                        "col1_revenues": Decimal("0"),
                        "col2_charges": Decimal("0"),
                        "col2_revenues": Decimal("0"),
                        "col3_charges": Decimal("0"),
                        "col3_revenues": Decimal("0"),
                    },
                ),
            ]
        )
        summary = build_summary(grouped)
        assert summary["totals"]["col1_charges"] == Decimal("800")

    def test_diff_is_revenues_minus_charges(self):
        summary = build_summary(self._grouped(col1_charges=Decimal("800"), col1_revenues=Decimal("1000")))
        assert summary["totals"]["col1_diff"] == Decimal("200")

    def test_diff_is_negative_when_excess_expense(self):
        summary = build_summary(self._grouped(col1_charges=Decimal("1000"), col1_revenues=Decimal("800")))
        assert summary["totals"]["col1_diff"] == Decimal("-200")

    def test_balanced_is_max_of_charges_and_revenues(self):
        summary = build_summary(self._grouped(col1_charges=Decimal("800"), col1_revenues=Decimal("1000")))
        assert summary["totals"]["balanced_col1"] == Decimal("1000")

    def test_rows_list_has_one_entry_per_grouped_key(self):
        grouped = OrderedDict(
            [
                (
                    1,
                    {
                        "label": "A",
                        **{
                            c: Decimal("0")
                            for c in (
                                "col1_charges",
                                "col1_revenues",
                                "col2_charges",
                                "col2_revenues",
                                "col3_charges",
                                "col3_revenues",
                            )
                        },
                    },
                ),
                (
                    2,
                    {
                        "label": "B",
                        **{
                            c: Decimal("0")
                            for c in (
                                "col1_charges",
                                "col1_revenues",
                                "col2_charges",
                                "col2_revenues",
                                "col3_charges",
                                "col3_revenues",
                            )
                        },
                    },
                ),
            ]
        )
        summary = build_summary(grouped)
        assert len(summary["rows"]) == TWO_ROWS


class TestNatureGroup:
    def test_two_digit_code_maps_directly(self):
        assert _nature_group(NATURE_30) == NATURE_30

    def test_three_digit_code_maps_to_first_two_digits(self):
        assert _nature_group(351) == NATURE_35

    def test_unknown_nature_returns_none(self):
        assert _nature_group(99) is None

    def test_none_input_returns_none(self):
        assert _nature_group(None) is None


class TestBuildNatureGrouped:
    def test_charges_account_accumulates_in_charges_column(self):
        ag = AccountGroupFactory()
        acc = AccountFactory(group=ag, nature="351")
        row = _row(acc, col1_charges=Decimal("1000"))

        result = build_nature_grouped([row])
        assert result[35]["col1_charges"] == Decimal("1000")

    def test_revenues_account_accumulates_in_revenues_column(self):
        ag = AccountGroupFactory()
        acc = AccountFactory(group=ag, nature="431")
        row = _row(acc, col1_revenues=Decimal("2000"))

        result = build_nature_grouped([row])
        assert result[43]["col1_revenues"] == Decimal("2000")

    def test_empty_nature_groups_are_pruned(self):
        ag = AccountGroupFactory()
        acc = AccountFactory(group=ag, nature="351")
        row = _row(acc, col1_charges=Decimal("1000"))

        result = build_nature_grouped([row])
        assert NATURE_35 in result
        assert NATURE_30 not in result

    def test_empty_rows_returns_empty_dict(self):
        result = build_nature_grouped([])
        assert result == OrderedDict()
