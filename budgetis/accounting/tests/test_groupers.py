from collections import OrderedDict
from decimal import Decimal

import pytest
from django.template.loader import render_to_string

from budgetis.accounting.groupers import _nature_group
from budgetis.accounting.groupers import build_grouped
from budgetis.accounting.groupers import build_nature_grouped
from budgetis.accounting.groupers import build_nature_tree
from budgetis.accounting.groupers import build_summary
from budgetis.accounting.nature import NATURE_GROUPS
from budgetis.accounting.tests.factories import AccountFactory
from budgetis.accounting.tests.factories import AccountGroupFactory
from budgetis.accounting.tests.factories import GroupResponsibilityFactory
from budgetis.accounting.tests.factories import NatureGroupFactory
from budgetis.accounting.views.data import AccountRow
from budgetis.common.models import ChartScheme
from budgetis.users.tests.factories import UserFactory


def _mch1_tree():
    """Build a 3-level MCH1 tree: level1 -> level2 -> level3 (leaf)."""
    level1 = AccountGroupFactory(level=1, parent=None)
    level2 = AccountGroupFactory(level=2, parent=level1)
    leaf = AccountGroupFactory(level=3, parent=level2)
    return level1, level2, leaf


pytestmark = pytest.mark.django_db

NATURE_30 = 30
NATURE_33 = 33
NATURE_35 = 35
NATURE_36 = 36
TWO_ACCOUNTS = 2
TWO_ROWS = 2


def _row(account, **col_kwargs) -> AccountRow:
    return AccountRow(account=account, **col_kwargs)


class TestBuildGrouped:
    def test_empty_rows_returns_empty_ordered_dict(self):
        assert build_grouped([], 2024) == OrderedDict()

    def test_accumulates_totals_at_all_hierarchy_levels(self):
        level1, level2, leaf = _mch1_tree()
        acc = AccountFactory(group=leaf)
        row = _row(acc, col1_charges=Decimal("500"), col1_revenues=Decimal("200"))

        result = build_grouped([row], 2024)

        level1_data = result[level1.code]
        level2_data = level1_data["children"][level2.code]
        leaf_data = level2_data["children"][leaf.code]
        assert level1_data["col1_charges"] == Decimal("500")
        assert level2_data["col1_charges"] == Decimal("500")
        assert leaf_data["col1_charges"] == Decimal("500")
        assert leaf_data["col1_revenues"] == Decimal("200")

    def test_two_rows_in_same_group_accumulate(self):
        level1, level2, leaf = _mch1_tree()
        acc1 = AccountFactory(group=leaf)
        acc2 = AccountFactory(group=leaf)
        row1 = _row(acc1, col1_charges=Decimal("300"))
        row2 = _row(acc2, col1_charges=Decimal("700"))

        result = build_grouped([row1, row2], 2024)
        leaf_data = result[level1.code]["children"][level2.code]["children"][leaf.code]
        assert leaf_data["col1_charges"] == Decimal("1000")
        assert len(leaf_data["accounts"]) == TWO_ACCOUNTS

    def test_row_without_group_is_skipped(self):
        acc = AccountFactory(group=None)
        row = _row(acc, col1_charges=Decimal("999"))
        assert build_grouped([row], 2024) == OrderedDict()

    def test_accounts_sorted_by_function_within_group(self):
        level1, level2, leaf = _mch1_tree()
        acc_b = AccountFactory(group=leaf, function="720", nature="351")
        acc_a = AccountFactory(group=leaf, function="460", nature="351")
        row_b = _row(acc_b, col1_charges=Decimal("100"))
        row_a = _row(acc_a, col1_charges=Decimal("200"))

        result = build_grouped([row_b, row_a], 2024)
        accounts = result[level1.code]["children"][level2.code]["children"][leaf.code]["accounts"]
        functions = [r.account.function for r in accounts]
        assert functions == sorted(functions)

    def test_four_level_mch2_tree_builds_through_same_path(self):
        level1 = AccountGroupFactory(scheme=ChartScheme.MCH2, level=1, parent=None, code="0")
        level2 = AccountGroupFactory(scheme=ChartScheme.MCH2, level=2, parent=level1, code="01")
        level3 = AccountGroupFactory(scheme=ChartScheme.MCH2, level=3, parent=level2, code="011")
        leaf = AccountGroupFactory(scheme=ChartScheme.MCH2, level=4, parent=level3, code="0110")
        acc = AccountFactory(scheme=ChartScheme.MCH2, group=leaf, function="01100")
        row = _row(acc, col1_charges=Decimal("500"))

        result = build_grouped([row], 2024)

        leaf_data = result[level1.code]["children"][level2.code]["children"][level3.code]["children"][leaf.code]
        assert leaf_data["col1_charges"] == Decimal("500")
        assert leaf_data["accounts"][0].account == acc


class TestDisplayResponsibleAggregation:
    """
    SuperGroup/MetaGroup nodes never have their own GroupResponsibility — they're
    purely a graphical grouping for the report. Their displayed `responsible` is
    derived bottom-up from the leaf (function) nodes underneath them.
    """

    def _two_leaves_under_shared_ancestors(self):
        level1 = AccountGroupFactory(level=1, parent=None)
        level2 = AccountGroupFactory(level=2, parent=level1)
        leaf_a = AccountGroupFactory(level=3, parent=level2)
        leaf_b = AccountGroupFactory(level=3, parent=level2)
        return level1, level2, leaf_a, leaf_b

    def test_ancestor_shows_shared_responsible_when_all_leaves_agree(self):
        level1, level2, leaf_a, leaf_b = self._two_leaves_under_shared_ancestors()
        user = UserFactory()
        GroupResponsibilityFactory(group=leaf_a, year=2024, responsible=user)
        GroupResponsibilityFactory(group=leaf_b, year=2024, responsible=user)
        acc_a = AccountFactory(group=leaf_a)
        acc_b = AccountFactory(group=leaf_b)
        rows = [_row(acc_a, col1_charges=Decimal("100")), _row(acc_b, col1_charges=Decimal("200"))]

        result = build_grouped(rows, 2024)

        level2_data = result[level1.code]["children"][level2.code]
        assert level2_data["responsible"] == user
        assert result[level1.code]["responsible"] == user

    def test_ancestor_shows_no_responsible_when_leaves_disagree(self):
        level1, level2, leaf_a, leaf_b = self._two_leaves_under_shared_ancestors()
        GroupResponsibilityFactory(group=leaf_a, year=2024, responsible=UserFactory())
        GroupResponsibilityFactory(group=leaf_b, year=2024, responsible=UserFactory())
        acc_a = AccountFactory(group=leaf_a)
        acc_b = AccountFactory(group=leaf_b)
        rows = [_row(acc_a, col1_charges=Decimal("100")), _row(acc_b, col1_charges=Decimal("200"))]

        result = build_grouped(rows, 2024)

        level2_data = result[level1.code]["children"][level2.code]
        assert level2_data["responsible"] is None
        assert result[level1.code]["responsible"] is None

    def test_ancestor_shows_none_when_no_leaf_has_a_responsible(self):
        level1, level2, leaf = _mch1_tree()
        acc = AccountFactory(group=leaf)
        row = _row(acc, col1_charges=Decimal("100"))

        result = build_grouped([row], 2024)

        assert result[level1.code]["children"][level2.code]["responsible"] is None
        assert result[level1.code]["responsible"] is None

    def test_leaf_keeps_its_own_responsible(self):
        level1, level2, leaf = _mch1_tree()
        user = UserFactory()
        GroupResponsibilityFactory(group=leaf, year=2024, responsible=user)
        acc = AccountFactory(group=leaf)
        row = _row(acc, col1_charges=Decimal("100"))

        result = build_grouped([row], 2024)

        leaf_data = result[level1.code]["children"][level2.code]["children"][leaf.code]
        assert leaf_data["responsible"] == user


class TestGroupNodeTemplateRendersBothDepths:
    """
    Proves account_list.html renders a 3-level MCH1 tree and a 4-level MCH2 tree
    through the exact same recursive group_node.html partial, with no
    scheme-specific branching in the view/template layer.
    """

    def _render(self, grouped: OrderedDict) -> str:
        return render_to_string(
            "accounting/partials/account_list.html",
            {"grouped": grouped, "global_summary": {"rows": [], "totals": {}}, "year": 2024},
        )

    def test_three_level_mch1_tree(self):
        _level1, _level2, leaf = _mch1_tree()
        acc = AccountFactory(group=leaf)
        row = _row(acc, col1_charges=Decimal("500"))
        html = self._render(build_grouped([row], 2024))

        assert html.count("<h2 ") == 1
        assert html.count("<h3 ") == 1
        assert html.count("<h4 ") == 0
        assert leaf.label in html

    def test_four_level_mch2_tree(self):
        level1 = AccountGroupFactory(scheme=ChartScheme.MCH2, level=1, parent=None, code="0")
        level2 = AccountGroupFactory(scheme=ChartScheme.MCH2, level=2, parent=level1, code="01")
        level3 = AccountGroupFactory(scheme=ChartScheme.MCH2, level=3, parent=level2, code="011")
        leaf = AccountGroupFactory(scheme=ChartScheme.MCH2, level=4, parent=level3, code="0110")
        acc = AccountFactory(scheme=ChartScheme.MCH2, group=leaf, function="01100")
        row = _row(acc, col1_charges=Decimal("500"))
        html = self._render(build_grouped([row], 2024))

        assert html.count("<h2 ") == 1
        assert html.count("<h3 ") == 1
        assert html.count("<h4 ") == 1
        assert leaf.label in html


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

    def test_mch2_rows_use_nature_group_model_label_over_hardcoded_dict(self):
        # NATURE_GROUPS (the MCH1 fallback) has no "34" entry at all, and its
        # "36" is mislabeled relative to the canton's official MCH2 reference -
        # both must come from NatureGroup instead for MCH2 rows.
        NatureGroupFactory(scheme=ChartScheme.MCH2, level=2, code="34", label="Charges financières")
        NatureGroupFactory(scheme=ChartScheme.MCH2, level=2, code="36", label="Charges de transferts")
        ag = AccountGroupFactory(scheme=ChartScheme.MCH2)
        acc = AccountFactory(scheme=ChartScheme.MCH2, group=ag, nature="3400")
        row = _row(acc, col1_charges=Decimal("500"))

        result = build_nature_grouped([row])

        assert result[34]["label"] == "Charges financières"
        assert result[34]["code"] == "34"
        assert result[34]["col1_charges"] == Decimal("500")
        # Unlike MCH1's broad NATURE_GROUPS, the official MCH2 set is small and
        # complete enough that an all-zero group is worth surfacing, not hiding.
        assert result[NATURE_36]["col1_charges"] == Decimal("0")

    def test_mch2_keeps_all_official_groups_even_when_all_zero(self):
        NatureGroupFactory(scheme=ChartScheme.MCH2, level=2, code="33", label="Amortissements")
        ag = AccountGroupFactory(scheme=ChartScheme.MCH2)
        acc = AccountFactory(scheme=ChartScheme.MCH2, group=ag, nature="3300", charges=Decimal("0"))
        row = _row(acc, col1_charges=Decimal("0"))

        result = build_nature_grouped([row])

        assert NATURE_33 in result
        assert result[NATURE_33]["col1_charges"] == Decimal("0")

    def test_mch1_rows_ignore_mch2_nature_group_rows(self):
        NatureGroupFactory(scheme=ChartScheme.MCH2, level=2, code="30", label="Should not apply to MCH1")
        ag = AccountGroupFactory(scheme=ChartScheme.MCH1)
        acc = AccountFactory(scheme=ChartScheme.MCH1, group=ag, nature="300")
        row = _row(acc, col1_charges=Decimal("500"))

        result = build_nature_grouped([row])

        assert result[30]["label"] == str(NATURE_GROUPS[30])


class TestBuildNatureTree:
    def test_empty_rows_returns_none(self):
        assert build_nature_tree([]) is None

    def test_mch1_rows_return_none(self):
        # NATURE_GROUPS (MCH1's fallback) has no level 1/3 data to build a tree
        # from - build_nature_grouped's flat table stays the report for it.
        ag = AccountGroupFactory(scheme=ChartScheme.MCH1)
        acc = AccountFactory(scheme=ChartScheme.MCH1, group=ag, nature="300")
        row = _row(acc, col1_charges=Decimal("500"))

        assert build_nature_tree([row]) is None

    def test_builds_three_level_tree_and_aggregates_up(self):
        level1 = NatureGroupFactory(level=1, code="3", label="Charges", parent=None)
        level2 = NatureGroupFactory(level=2, code="30", label="Charges de personnel", parent=level1)
        NatureGroupFactory(level=3, code="300", label="Autorités et commissions", parent=level2)
        ag = AccountGroupFactory(scheme=ChartScheme.MCH2)
        acc = AccountFactory(scheme=ChartScheme.MCH2, group=ag, nature="3000")
        row = _row(acc, col1_charges=Decimal("500"))

        tree = build_nature_tree([row])

        assert tree is not None
        l1 = tree["3"]
        assert l1["label"] == "Charges"
        assert l1["col1_charges"] == Decimal("500")
        l2 = l1["children"]["30"]
        assert l2["label"] == "Charges de personnel"
        assert l2["col1_charges"] == Decimal("500")
        l3 = l2["children"]["300"]
        assert l3["label"] == "Autorités et commissions"
        assert l3["col1_charges"] == Decimal("500")
        assert l3["children"] == OrderedDict()

    def test_keeps_all_official_groups_even_when_all_zero(self):
        level1 = NatureGroupFactory(level=1, code="3", label="Charges", parent=None)
        NatureGroupFactory(level=2, code="30", label="Charges de personnel", parent=level1)
        NatureGroupFactory(level=2, code="31", label="Biens et services", parent=level1)
        ag = AccountGroupFactory(scheme=ChartScheme.MCH2)
        acc = AccountFactory(scheme=ChartScheme.MCH2, group=ag, nature="3000")
        row = _row(acc, col1_charges=Decimal("500"))

        tree = build_nature_tree([row])

        assert tree is not None
        assert "31" in tree["3"]["children"]
        assert tree["3"]["children"]["31"]["col1_charges"] == Decimal("0")

    def test_unmatched_nature_is_dropped_silently(self):
        level1 = NatureGroupFactory(level=1, code="3", label="Charges", parent=None)
        NatureGroupFactory(level=2, code="30", label="Charges de personnel", parent=level1)
        ag = AccountGroupFactory(scheme=ChartScheme.MCH2)
        acc = AccountFactory(scheme=ChartScheme.MCH2, group=ag, nature="9999")
        row = _row(acc, col1_charges=Decimal("500"))

        tree = build_nature_tree([row])

        assert tree is not None
        totals = sum(l1["col1_charges"] for l1 in tree.values())
        assert totals == Decimal("0")
