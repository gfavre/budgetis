import pytest

from budgetis.accounting.forms import AccountFilterForm
from budgetis.accounting.forms import NatureFilterForm
from budgetis.accounting.forms import YearFilterForm
from budgetis.users.tests.factories import UserFactory


pytestmark = pytest.mark.django_db


class TestAccountFilterFormOnlyResponsibleField:
    def test_present_for_a_municipal_user(self):
        form = AccountFilterForm(user=UserFactory(is_municipal=True))

        assert "only_responsible" in form.fields

    def test_absent_for_a_non_municipal_user(self):
        # A Bourse member has no "own accounts" - GroupResponsibility is a
        # municipal officer's concept - so the checkbox shouldn't even appear.
        form = AccountFilterForm(user=UserFactory(is_municipal=False))

        assert "only_responsible" not in form.fields

    def test_present_when_no_user_is_given(self):
        form = AccountFilterForm()

        assert "only_responsible" in form.fields


class TestYearFilterForm:
    """Used by the staged result - an aggregate report, not a per-account listing where "only my accounts" applies."""

    def test_has_no_only_responsible_field_at_all(self):
        form = YearFilterForm(user=UserFactory(is_municipal=True))

        assert "only_responsible" not in form.fields
        assert list(form.fields) == ["year"]

    def test_accepts_a_user_kwarg_without_using_it(self):
        # Interface parity with AccountFilterForm - BaseExplorerView always
        # passes user=, regardless of which form_class a view sets.
        form = YearFilterForm(user=UserFactory(is_municipal=False))

        assert list(form.fields) == ["year"]


class TestNatureFilterForm:
    """By-nature reports group every account by nature regardless of who's responsible - same as YearFilterForm."""

    def test_has_no_only_responsible_field_even_for_a_municipal_user(self):
        form = NatureFilterForm(user=UserFactory(is_municipal=True))

        assert "only_responsible" not in form.fields
        assert set(form.fields) == {"year", "detail"}
