from decimal import Decimal

import pytest

from budgetis.accounting.tests.factories import AccountCommentFactory
from budgetis.accounting.tests.factories import AccountFactory
from budgetis.accounting.tests.factories import AccountGroupFactory


pytestmark = pytest.mark.django_db


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


class TestAccountComment:
    def test_str_includes_author_and_account(self):
        comment = AccountCommentFactory()
        assert str(comment.author) in str(comment)
        assert str(comment.account) in str(comment)
