from decimal import Decimal

import pytest
from django.core.management import call_command
from django.db.models import ProtectedError

from budgetis.accounting.models import AccountGroup
from budgetis.accounting.models import NatureGroup
from budgetis.accounting.tests.factories import AccountCodeMappingFactory
from budgetis.accounting.tests.factories import AccountCommentFactory
from budgetis.accounting.tests.factories import AccountFactory
from budgetis.accounting.tests.factories import AccountGroupFactory
from budgetis.accounting.tests.factories import NatureGroupFactory
from budgetis.common.models import ChartScheme


pytestmark = pytest.mark.django_db

TWO_GROUPS = 2


class TestAccountFullCode:
    def test_without_sub_account(self):
        acc = AccountFactory.build(function="720", nature="351", sub_account="")
        assert acc.full_code == "720.351"

    def test_with_sub_account(self):
        acc = AccountFactory.build(function="720", nature="351", sub_account="1")
        assert acc.full_code == "720.351.1"


class TestAccountProperties:
    # is_funding_request and is_depreciation compare FUNDING_REQUEST_GTE (int)
    # against self.nature. These properties only work when nature is stored as an
    # integer (in-memory, before DB round-trip). Use build() to stay in-memory.
    def test_is_funding_request_when_in_range(self):
        acc = AccountFactory.build(nature=500)
        assert acc.is_funding_request is True

    def test_is_not_funding_request_below_range(self):
        acc = AccountFactory.build(nature=350)
        assert acc.is_funding_request is False

    def test_is_not_funding_request_above_range(self):
        acc = AccountFactory.build(nature=600)
        assert acc.is_funding_request is False

    def test_is_depreciation_when_in_range(self):
        acc = AccountFactory.build(nature=630)
        assert acc.is_depreciation is True

    def test_is_not_depreciation_below_range(self):
        acc = AccountFactory.build(nature=350)
        assert acc.is_depreciation is False

    def test_is_not_depreciation_above_range(self):
        acc = AccountFactory.build(nature=700)
        assert acc.is_depreciation is False

    def test_absolute_value_uses_charges_when_nonzero(self):
        acc = AccountFactory.build(charges=Decimal("1500.00"), revenues=Decimal("0.00"))
        assert acc.absolute_value == Decimal("1500.00")

    def test_absolute_value_negates_negative_charges(self):
        acc = AccountFactory.build(charges=Decimal("-1500.00"), revenues=Decimal("0.00"))
        assert acc.absolute_value == Decimal("1500.00")

    def test_absolute_value_falls_back_to_revenues_when_charges_zero(self):
        acc = AccountFactory.build(charges=Decimal("0.00"), revenues=Decimal("2000.00"))
        assert acc.absolute_value == Decimal("2000.00")


class TestAccountSave:
    def test_auto_assigns_group_from_function_code(self):
        group = AccountGroupFactory(code="720")
        acc = AccountFactory.build(function="720", group=None)
        acc.save()
        acc.refresh_from_db()
        assert acc.group == group

    def test_preserves_explicitly_set_group(self):
        group = AccountGroupFactory()
        acc = AccountFactory(group=group)
        assert acc.group == group

    def test_auto_assigns_mch2_group_from_four_digit_prefix(self):
        group = AccountGroupFactory(scheme=ChartScheme.MCH2, level=4, code="0110")
        acc = AccountFactory.build(scheme=ChartScheme.MCH2, function="01100", group=None)
        acc.save()
        acc.refresh_from_db()
        assert acc.group == group

    def test_ignores_a_same_code_collision_at_another_level(self):
        # A group's code is only unique within its own level - a stray/unrelated
        # group at a shallower level sharing the same code string must not make
        # the deepest-level lookup raise MultipleObjectsReturned.
        AccountGroupFactory(scheme=ChartScheme.MCH2, level=2, code="0110")
        leaf = AccountGroupFactory(scheme=ChartScheme.MCH2, level=4, code="0110")
        acc = AccountFactory.build(scheme=ChartScheme.MCH2, function="01100", group=None)
        acc.save()
        acc.refresh_from_db()
        assert acc.group == leaf


class TestAccountGroupHierarchy:
    def test_same_code_coexists_across_schemes_and_levels(self):
        mch1_root = AccountGroupFactory(scheme=ChartScheme.MCH1, level=1, code="1", parent=None)
        mch2_root = AccountGroupFactory(scheme=ChartScheme.MCH2, level=1, code="1", parent=None)
        assert mch1_root.id != mch2_root.id
        assert AccountGroup.objects.filter(code="1").count() == TWO_GROUPS

    def test_deleting_a_parent_with_children_is_protected(self):
        parent = AccountGroupFactory(level=1, parent=None)
        AccountGroupFactory(level=2, parent=parent)
        with pytest.raises(ProtectedError):
            parent.delete()


class TestAccountGroupFixture:
    """
    Locks in that the accountgroup_mch2 fixture (the canton's official
    functional classification, dumped with --natural-foreign
    --natural-primary) stays loadable and its parent links resolve correctly
    through natural keys. See docs/mch2-migration.md for the documented shape.
    """

    MCH2_ACCOUNTGROUP_COUNT = 418

    def test_loads_and_wires_parents_by_natural_key(self):
        call_command("loaddata", "accountgroup_mch2")

        assert AccountGroup.objects.filter(scheme=ChartScheme.MCH2).count() == self.MCH2_ACCOUNTGROUP_COUNT
        leaf = AccountGroup.objects.get(scheme=ChartScheme.MCH2, level=4, code="0110")
        level3 = leaf.parent
        assert level3 is not None
        assert level3.code == "011"
        level2 = level3.parent
        assert level2 is not None
        assert level2.code == "01"
        level1 = level2.parent
        assert level1 is not None
        assert level1.code == "0"


class TestNatureGroupHierarchy:
    def test_same_code_coexists_with_an_account_group(self):
        # NatureGroup is a separate table precisely so a nature code like "30"
        # doesn't collide with the unrelated function group of the same code.
        AccountGroupFactory(scheme=ChartScheme.MCH2, level=1, code="30", parent=None)
        nature_group = NatureGroupFactory(scheme=ChartScheme.MCH2, level=2, code="30", parent=None)
        assert nature_group.id is not None

    def test_deleting_a_parent_with_children_is_protected(self):
        parent = NatureGroupFactory(level=1, parent=None)
        NatureGroupFactory(level=2, parent=parent)
        with pytest.raises(ProtectedError):
            parent.delete()


class TestNatureGroupFixture:
    """
    Locks in that the naturegroup_mch2 fixture (dumped with --natural-foreign
    --natural-primary from the official import) stays loadable and that its
    self-referential parent links resolve correctly through natural keys.
    """

    MCH2_NATUREGROUP_COUNT = 421

    def test_loads_and_wires_parents_by_natural_key(self):
        call_command("loaddata", "naturegroup_mch2")

        assert NatureGroup.objects.filter(scheme=ChartScheme.MCH2).count() == self.MCH2_NATUREGROUP_COUNT
        leaf = NatureGroup.objects.get(scheme=ChartScheme.MCH2, level=4, code="3010")
        level3 = leaf.parent
        assert level3 is not None
        assert level3.code == "301"
        level2 = level3.parent
        assert level2 is not None
        assert level2.code == "30"
        level1 = level2.parent
        assert level1 is not None
        assert level1.code == "3"


class TestAccountComment:
    def test_str_includes_author_and_account(self):
        comment = AccountCommentFactory()
        assert str(comment.author) in str(comment)
        assert str(comment.account) in str(comment)


class TestAccountCodeMapping:
    def test_mch1_code_without_sub_account(self):
        mapping = AccountCodeMappingFactory(mch1_function="100", mch1_nature="301", mch1_sub_account="")
        assert mapping.mch1_code == "100.301"

    def test_mch1_code_with_sub_account(self):
        mapping = AccountCodeMappingFactory(mch1_function="110", mch1_nature="365", mch1_sub_account="1")
        assert mapping.mch1_code == "110.365.1"

    def test_mch2_code(self):
        mapping = AccountCodeMappingFactory(mch2_function="01100", mch2_nature="3010", mch2_sub_account="")
        assert mapping.mch2_code == "01100.3010"

    def test_str_shows_both_codes(self):
        mapping = AccountCodeMappingFactory(
            mch1_function="100",
            mch1_nature="301",
            mch1_sub_account="",
            mch2_function="01100",
            mch2_nature="3010",
            mch2_sub_account="",
        )
        assert str(mapping) == "100.301 -> 01100.3010"
