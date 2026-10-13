from http import HTTPStatus

import pytest
from django.urls import reverse

from budgetis.accounting.models import FunctionCategory
from budgetis.accounting.models import FunctionSplit
from budgetis.accounting.models import GroupResponsibility
from budgetis.accounting.tests.factories import AccountFactory
from budgetis.accounting.tests.factories import AccountGroupFactory
from budgetis.accounting.tests.factories import FunctionCategoryFactory
from budgetis.accounting.tests.factories import FunctionSplitFactory
from budgetis.accounting.tests.factories import GroupResponsibilityFactory
from budgetis.common.models import ChartScheme
from budgetis.users.tests.factories import BourseGroupFactory
from budgetis.users.tests.factories import UserFactory


pytestmark = pytest.mark.django_db
ASSIGNMENT_YEAR = 2027


@pytest.fixture(params=["admin", "bourse"])
def manager(request):
    user = UserFactory(is_staff=request.param == "admin")
    if request.param == "bourse":
        user.groups.add(BourseGroupFactory())
    return user


@pytest.fixture
def group():
    return AccountGroupFactory(scheme=ChartScheme.MCH2, level=4, code="9630")


def category_data(*, function="96301", label="Maison gothique", enabled=True):
    data = {
        "categories-TOTAL_FORMS": "1",
        "categories-INITIAL_FORMS": "0",
        "categories-MIN_NUM_FORMS": "0",
        "categories-MAX_NUM_FORMS": "1000",
        "categories-0-function": function,
        "categories-0-label": label,
    }
    if enabled:
        data["enabled"] = "on"
    return data


class SettingsAccessTests:
    def url(self):
        raise NotImplementedError

    def test_login_required(self, client):
        url = self.url()
        response = client.get(url)
        assert response.status_code == HTTPStatus.FOUND
        assert response.url.endswith(f"?next={url}")

    @pytest.mark.parametrize("method", ["get", "post"])
    def test_regular_user_forbidden(self, client, method, site_configuration_with_logo):
        client.force_login(UserFactory(is_municipal=True))
        response = getattr(client, method)(self.url())
        assert response.status_code == HTTPStatus.FORBIDDEN

    def test_authorized_get(self, client, manager, site_configuration_with_logo):
        client.force_login(manager)
        assert client.get(self.url()).status_code == HTTPStatus.OK


class TestResponsibilitySettingsView(SettingsAccessTests):
    def url(self):
        return reverse("accounting:responsibility-settings")

    def test_filters_and_paginates(self, client, manager, site_configuration_with_logo):
        GroupResponsibilityFactory.create_batch(26, year=2026)
        target = GroupResponsibilityFactory(year=2027)
        client.force_login(manager)
        response = client.get(self.url())
        assert response.context["is_paginated"]
        response = client.get(self.url(), {"year": "2027", "q": target.group.code})
        assert list(response.context["assignments"]) == [target]


class TestResponsibilityCreateView(SettingsAccessTests):
    def url(self):
        return reverse("accounting:responsibility-add")

    @pytest.mark.parametrize("function", ["", "96301"])
    def test_assigns_group_or_function(self, client, manager, group, function):
        AccountFactory(group=group, scheme=ChartScheme.MCH2, function="96301", year=2027)
        responsible = UserFactory()
        client.force_login(manager)
        response = client.post(
            self.url(), {"group": group.pk, "year": 2027, "function": function, "responsible": responsible.pk}
        )
        assert response.status_code == HTTPStatus.FOUND
        assert GroupResponsibility.objects.get(group=group, year=2027, function=function).responsible == responsible

    def test_rejects_wrong_function_and_duplicate(self, client, manager, group, site_configuration_with_logo):
        existing = GroupResponsibilityFactory(group=group, year=2027)
        client.force_login(manager)
        data = {"group": group.pk, "year": 2027, "function": "02901", "responsible": manager.pk}
        response = client.post(self.url(), data)
        assert "function" in response.context["form"].errors
        data["function"] = ""
        response = client.post(self.url(), data)
        assert response.context["form"].non_field_errors()
        existing.refresh_from_db()
        assert existing.responsible != manager


class TestResponsibilityUpdateView(SettingsAccessTests):
    def url(self):
        return reverse("accounting:responsibility-edit", args=[GroupResponsibilityFactory().pk])

    def test_changes_owner_preserving_scope_and_overrides(self, client, manager, group):
        assignment = GroupResponsibilityFactory(group=group, year=2027)
        override = GroupResponsibilityFactory(group=group, year=2027, function="96301")
        owner = UserFactory()
        client.force_login(manager)
        response = client.post(
            reverse("accounting:responsibility-edit", args=[assignment.pk]),
            {"responsible": owner.pk, "group": "99999", "year": "1900", "function": "invalid"},
        )
        assert response.status_code == HTTPStatus.FOUND
        assignment.refresh_from_db()
        override.refresh_from_db()
        assert assignment.responsible == owner
        assert assignment.group == group
        assert assignment.year == ASSIGNMENT_YEAR
        assert assignment.function == ""
        assert override.responsible != owner


class TestResponsibilityDeleteView(SettingsAccessTests):
    def url(self):
        return reverse("accounting:responsibility-delete", args=[GroupResponsibilityFactory().pk])

    def test_deletes_only_function_exception(self, client, manager, group, site_configuration_with_logo):
        default = GroupResponsibilityFactory(group=group, year=2027)
        override = GroupResponsibilityFactory(group=group, year=2027, function="96301")
        url = reverse("accounting:responsibility-delete", args=[override.pk])
        client.force_login(manager)
        assert client.get(url).status_code == HTTPStatus.OK
        assert GroupResponsibility.objects.filter(pk=override.pk).exists()
        assert client.post(url).status_code == HTTPStatus.FOUND
        assert not GroupResponsibility.objects.filter(pk=override.pk).exists()
        assert GroupResponsibility.objects.filter(pk=default.pk).exists()


class TestFunctionSplitSettingsView(SettingsAccessTests):
    def url(self):
        return reverse("accounting:function-split-settings")

    def test_lists_only_n4_mch2_and_searches(self, client, manager, group, site_configuration_with_logo):
        AccountGroupFactory()
        AccountGroupFactory(scheme=ChartScheme.MCH2, level=3, code="963")
        client.force_login(manager)
        response = client.get(self.url(), {"q": "9630"})
        assert list(response.context["groups"]) == [group]


class TestFunctionSplitUpdateView(SettingsAccessTests):
    def url(self):
        group = AccountGroupFactory(scheme=ChartScheme.MCH2, level=4, code="9630")
        return reverse("accounting:function-split-edit", args=[group.pk])

    def test_creates_split_and_label(self, client, manager, group):
        client.force_login(manager)
        response = client.post(reverse("accounting:function-split-edit", args=[group.pk]), category_data())
        assert response.status_code == HTTPStatus.FOUND
        split = FunctionSplit.objects.get(group=group)
        assert split.enabled
        assert split.categories.get(function="96301").label == "Maison gothique"

    def test_suggests_existing_functions_without_writing_on_get(
        self, client, manager, group, site_configuration_with_logo
    ):
        AccountFactory(group=group, scheme=ChartScheme.MCH2, function="96301")
        AccountFactory(group=group, scheme=ChartScheme.MCH2, function="96302")
        client.force_login(manager)
        response = client.get(reverse("accounting:function-split-edit", args=[group.pk]))
        assert [form.initial.get("function") for form in response.context["formset"]] == ["96301", "96302", None]
        assert not FunctionSplit.objects.exists()

    def test_unchanged_suggestions_do_not_require_labels(self, client, manager, group):
        AccountFactory(group=group, scheme=ChartScheme.MCH2, function="96301")
        client.force_login(manager)
        response = client.post(reverse("accounting:function-split-edit", args=[group.pk]), category_data(label=""))
        assert response.status_code == HTTPStatus.FOUND
        assert not FunctionCategory.objects.exists()

    @pytest.mark.parametrize("function", ["02901", "9630a", "9630"])
    def test_invalid_new_category_rolls_back_entire_configuration(
        self, client, manager, group, function, site_configuration_with_logo
    ):
        client.force_login(manager)
        response = client.post(
            reverse("accounting:function-split-edit", args=[group.pk]), category_data(function=function)
        )
        assert response.context["formset"].errors[0]
        assert not FunctionSplit.objects.exists()
        assert not FunctionCategory.objects.exists()

    def test_disabling_retains_labels_and_allows_editing(self, client, manager, group):
        category = FunctionCategoryFactory(split=FunctionSplitFactory(group=group))
        data = category_data(label="New name", enabled=False)
        data.update({"categories-INITIAL_FORMS": "1", "categories-0-id": category.pk})
        client.force_login(manager)
        response = client.post(reverse("accounting:function-split-edit", args=[group.pk]), data)
        assert response.status_code == HTTPStatus.FOUND
        category.refresh_from_db()
        assert category.label == "New name"
        assert not category.split.enabled

    def test_delete_label_preserves_split(self, client, manager, group):
        category = FunctionCategoryFactory(split=FunctionSplitFactory(group=group))
        data = category_data()
        data.update({"categories-INITIAL_FORMS": "1", "categories-0-id": category.pk, "categories-0-DELETE": "on"})
        client.force_login(manager)
        assert (
            client.post(reverse("accounting:function-split-edit", args=[group.pk]), data).status_code
            == HTTPStatus.FOUND
        )
        assert not FunctionCategory.objects.exists()
        assert FunctionSplit.objects.get(group=group).enabled

    def test_cannot_edit_other_groups_category(self, client, manager, group, site_configuration_with_logo):
        other = AccountGroupFactory(scheme=ChartScheme.MCH2, level=4, code="0290")
        category = FunctionCategoryFactory(split=FunctionSplitFactory(group=other), function="02901")
        FunctionSplitFactory(group=group)
        data = category_data(label="Changed")
        data.update({"categories-INITIAL_FORMS": "1", "categories-0-id": category.pk})
        client.force_login(manager)
        response = client.post(reverse("accounting:function-split-edit", args=[group.pk]), data)
        assert response.status_code == HTTPStatus.OK
        category.refresh_from_db()
        assert category.label != "Changed"

    def test_non_n4_group_not_found(self, client, manager):
        client.force_login(manager)
        group = AccountGroupFactory()
        assert (
            client.get(reverse("accounting:function-split-edit", args=[group.pk])).status_code == HTTPStatus.NOT_FOUND
        )


class TestPlatformSettingsMenu:
    def test_role_gates_menu_and_links(self, client, manager, site_configuration_with_logo):
        client.force_login(manager)
        response = client.get(reverse("home"))
        html = response.content.decode()
        assert 'id="platform-settings-menu"' in html
        assert reverse("accounting:responsibility-settings") in html
        assert reverse("accounting:function-split-settings") in html

    def test_regular_and_anonymous_users_have_no_menu(self, client, site_configuration_with_logo):
        assert 'id="platform-settings-menu"' not in client.get(reverse("home")).content.decode()
        client.force_login(UserFactory())
        assert 'id="platform-settings-menu"' not in client.get(reverse("home")).content.decode()
