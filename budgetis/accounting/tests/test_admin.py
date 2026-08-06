from http import HTTPStatus

import pytest
from django.contrib.admin import helpers
from django.urls import reverse

from budgetis.accounting.models import GroupResponsibility
from budgetis.accounting.tests.factories import AccountFactory
from budgetis.accounting.tests.factories import AccountGroupFactory
from budgetis.accounting.tests.factories import AvailableYearFactory
from budgetis.accounting.tests.factories import GroupResponsibilityFactory
from budgetis.users.tests.factories import UserFactory


pytestmark = pytest.mark.django_db


class TestAccountAdminReassignResponsible:
    def test_shows_confirmation_form(self, admin_client):
        account = AccountFactory(year=2026)
        url = reverse("admin:accounting_account_changelist")

        response = admin_client.post(
            url,
            data={"action": "reassign_responsible", helpers.ACTION_CHECKBOX_NAME: [account.pk]},
        )

        assert response.status_code == HTTPStatus.OK
        assert "form" in response.context

    def test_creates_responsibility_for_selected_account_year(self, admin_client):
        user = UserFactory(trigram="ADA")
        group = AccountGroupFactory(code="720")
        account = AccountFactory(year=2026, group=group, function="720")
        url = reverse("admin:accounting_account_changelist")

        admin_client.post(
            url,
            data={
                "action": "reassign_responsible",
                helpers.ACTION_CHECKBOX_NAME: [account.pk],
                "apply": "Confirm",
                "responsible": user.pk,
            },
        )

        responsibility = GroupResponsibility.objects.get(group=group, year=2026)
        assert responsibility.responsible == user

    def test_ignores_accounts_without_a_group(self, admin_client):
        user = UserFactory(trigram="ADA")
        account = AccountFactory(year=2026, group=None)
        url = reverse("admin:accounting_account_changelist")

        admin_client.post(
            url,
            data={
                "action": "reassign_responsible",
                helpers.ACTION_CHECKBOX_NAME: [account.pk],
                "apply": "Confirm",
                "responsible": user.pk,
            },
        )

        assert not GroupResponsibility.objects.exists()

    def test_deduplicates_groups_across_selected_accounts(self, admin_client):
        user = UserFactory(trigram="ADA")
        group = AccountGroupFactory(code="720")
        budget = AccountFactory(year=2026, group=group, function="720", nature="351", is_budget=True)
        actual = AccountFactory(year=2026, group=group, function="720", nature="352", is_budget=False)
        url = reverse("admin:accounting_account_changelist")

        admin_client.post(
            url,
            data={
                "action": "reassign_responsible",
                helpers.ACTION_CHECKBOX_NAME: [budget.pk, actual.pk],
                "apply": "Confirm",
                "responsible": user.pk,
            },
        )

        assert GroupResponsibility.objects.filter(group=group, year=2026).count() == 1


class TestAccountGroupAdminReassignResponsible:
    def test_shows_confirmation_form_with_year_field(self, admin_client):
        group = AccountGroupFactory()
        url = reverse("admin:accounting_accountgroup_changelist")

        response = admin_client.post(
            url,
            data={"action": "reassign_responsible", helpers.ACTION_CHECKBOX_NAME: [group.pk]},
        )

        assert response.status_code == HTTPStatus.OK
        assert "year" in response.context["form"].fields

    def test_creates_responsibility_for_chosen_year(self, admin_client):
        AvailableYearFactory(year=2026)
        user = UserFactory(trigram="ADA")
        group = AccountGroupFactory(code="720")
        url = reverse("admin:accounting_accountgroup_changelist")

        admin_client.post(
            url,
            data={
                "action": "reassign_responsible",
                helpers.ACTION_CHECKBOX_NAME: [group.pk],
                "apply": "Confirm",
                "responsible": user.pk,
                "year": "2026",
            },
        )

        responsibility = GroupResponsibility.objects.get(group=group, year=2026)
        assert responsibility.responsible == user

    def test_updates_existing_responsibility(self, admin_client):
        AvailableYearFactory(year=2026)
        old_user = UserFactory(trigram="PCO")
        new_user = UserFactory(trigram="ADA")
        group = AccountGroupFactory(code="720")
        GroupResponsibilityFactory(group=group, year=2026, responsible=old_user)
        url = reverse("admin:accounting_accountgroup_changelist")

        admin_client.post(
            url,
            data={
                "action": "reassign_responsible",
                helpers.ACTION_CHECKBOX_NAME: [group.pk],
                "apply": "Confirm",
                "responsible": new_user.pk,
                "year": "2026",
            },
        )

        responsibility = GroupResponsibility.objects.get(group=group, year=2026)
        assert responsibility.responsible == new_user
