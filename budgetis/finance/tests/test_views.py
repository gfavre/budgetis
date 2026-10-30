from decimal import Decimal
from http import HTTPStatus
from typing import cast

import pytest
from django.contrib.auth.models import Permission
from django.db import IntegrityError
from django.test import Client
from django.urls import reverse
from django.utils.translation import gettext

from budgetis.accounting.tests.factories import AccountFactory
from budgetis.accounting.tests.factories import AvailableYearFactory
from budgetis.common.models import ChartScheme
from budgetis.finance.forms import DUPLICATE_CATEGORY_ERROR
from budgetis.finance.forms import DUPLICATE_EXACT_CODE_ERROR
from budgetis.finance.forms import SankeyAccountCodeRuleForm
from budgetis.finance.forms import SankeyCategoryForm
from budgetis.finance.models import AvailableYear
from budgetis.finance.models import SankeyAccountCodeRule
from budgetis.finance.models import SankeyCategory
from budgetis.finance.models import SankeyFlow
from budgetis.finance.models import SankeyNatureRangeRule
from budgetis.finance.tests.factories import SankeyAccountCodeRuleFactory
from budgetis.finance.tests.factories import SankeyCategoryFactory
from budgetis.finance.tests.factories import SankeyFunctionNatureRuleFactory
from budgetis.finance.tests.factories import SankeyLabelRuleFactory
from budgetis.finance.tests.factories import SankeyNatureRangeRuleFactory
from budgetis.users.tests.factories import UserFactory


pytestmark = pytest.mark.django_db

LOGIN_URL = "/accounts/login/"
EXACT_CODE_INPUT = {"function": "02904", "nature": "4472", "sub_account": "01"}
DUPLICATE_CATEGORY_NAME = "Prélèvement réserve de politique budgétaire"
RULE_FACTORIES = {
    "nature-range": SankeyNatureRangeRuleFactory,
    "function-nature": SankeyFunctionNatureRuleFactory,
    "account-code": SankeyAccountCodeRuleFactory,
    "label": SankeyLabelRuleFactory,
}


@pytest.fixture(params=[(kind, scheme) for kind in RULE_FACTORIES for scheme in ChartScheme.values])
def sankey_rule_case(request):
    kind, scheme = request.param
    return kind, RULE_FACTORIES[kind](scheme=scheme)


def _grant_view_sankey_category(user):
    permission = Permission.objects.get(codename="view_sankeycategory", content_type__app_label="finance")
    user.user_permissions.add(permission)


def _grant_change_sankey_category(user):
    permission = Permission.objects.get(codename="change_sankeycategory", content_type__app_label="finance")
    user.user_permissions.add(permission)


def _make_category(**kwargs) -> SankeyCategory:
    """factory_boy's DjangoModelFactory has no type stubs, so mypy infers the
    factory class itself rather than the model - cast once here instead of
    on every call site that needs `.pk`/`.refresh_from_db()`."""
    return cast("SankeyCategory", SankeyCategoryFactory(**kwargs))


def _make_nature_range_rule(**kwargs) -> SankeyNatureRangeRule:
    return cast("SankeyNatureRangeRule", SankeyNatureRangeRuleFactory(**kwargs))


class TestSankeyView:
    def test_login_required(self, client):
        response = client.get(reverse("finance:index"))
        assert response.status_code == HTTPStatus.FOUND
        assert LOGIN_URL in response.url

    def test_authenticated_returns_200(self, client, site_configuration_with_logo):
        client.force_login(UserFactory())
        response = client.get(reverse("finance:index"))
        assert response.status_code == HTTPStatus.OK

    def test_available_years_carry_their_scheme(self, client, site_configuration_with_logo):
        AvailableYearFactory(year=2026, type=AvailableYear.YearType.BUDGET, scheme=ChartScheme.MCH2)
        AvailableYearFactory(year=2025, type=AvailableYear.YearType.ACTUAL, scheme=ChartScheme.MCH1)
        client.force_login(UserFactory())

        response = client.get(reverse("finance:index"))

        by_year = {row["year"]: row["scheme"] for row in response.context["available_years"]}
        assert by_year[2026] == ChartScheme.MCH2
        assert by_year[2025] == ChartScheme.MCH1

    def test_regular_user_does_not_see_the_settings_link(self, client, site_configuration_with_logo):
        client.force_login(UserFactory())

        response = client.get(reverse("finance:index"))

        assert reverse("finance:sankey-rules") not in response.content.decode()

    def test_user_with_permission_sees_the_settings_link(self, client, site_configuration_with_logo):
        user = UserFactory()
        _grant_view_sankey_category(user)
        client.force_login(user)

        response = client.get(reverse("finance:index"))

        assert reverse("finance:sankey-rules") in response.content.decode()


class TestSankeyRulesView:
    @pytest.mark.parametrize("can_change", [False, True])
    def test_rule_actions_follow_edit_permission(
        self, client, site_configuration_with_logo, sankey_rule_case, can_change
    ):
        kind, rule = sankey_rule_case
        user = UserFactory()
        _grant_view_sankey_category(user)
        if can_change:
            _grant_change_sankey_category(user)
        client.force_login(user)

        response = client.get(reverse("finance:sankey-rules"), {"scheme": rule.scheme})

        html = response.content.decode()
        for action in ("edit", "delete"):
            url = reverse(f"finance:sankey-rule-{action}", args=[kind, rule.pk])
            assert (url in html) == can_change
        add_url = reverse("finance:sankey-rule-add", args=[kind, rule.category_id])
        assert (add_url in html) == can_change
        category_url = reverse("finance:sankey-category-edit", args=[rule.category_id])
        assert (category_url in html) == can_change

    def test_login_required(self, client):
        response = client.get(reverse("finance:sankey-rules"))
        assert response.status_code == HTTPStatus.FOUND
        assert LOGIN_URL in response.url

    def test_authenticated_without_permission_is_forbidden(self, client):
        client.force_login(UserFactory())
        response = client.get(reverse("finance:sankey-rules"))
        assert response.status_code == HTTPStatus.FORBIDDEN

    def test_authenticated_with_permission_returns_200(self, client, site_configuration_with_logo):
        user = UserFactory()
        _grant_view_sankey_category(user)
        client.force_login(user)

        response = client.get(reverse("finance:sankey-rules"), {"scheme": ChartScheme.MCH1})

        assert response.status_code == HTTPStatus.OK

    def test_invalid_scheme_falls_back_to_a_valid_default(self, client, site_configuration_with_logo):
        user = UserFactory()
        _grant_view_sankey_category(user)
        client.force_login(user)

        response = client.get(reverse("finance:sankey-rules"), {"scheme": "not-a-scheme"})

        assert response.status_code == HTTPStatus.OK
        assert response.context["scheme"] in ChartScheme.values

    def test_category_rules_are_filtered_by_scheme_and_grouped_by_flow(self, client, site_configuration_with_logo):
        user = UserFactory()
        _grant_view_sankey_category(user)
        client.force_login(user)
        category = _make_category(flow=SankeyFlow.COMMUNE)
        mch1_rule = SankeyNatureRangeRuleFactory(
            scheme=ChartScheme.MCH1, nature_start=9000, nature_end=9009, category=category
        )
        SankeyNatureRangeRuleFactory(scheme=ChartScheme.MCH2, nature_start=9000, nature_end=9009, category=category)
        SankeyFunctionNatureRuleFactory(
            scheme=ChartScheme.MCH1, function_prefix="90", nature_start=9000, nature_end=9000, category=category
        )

        response = client.get(reverse("finance:sankey-rules"), {"scheme": ChartScheme.MCH1})

        flow_groups = response.context["flow_groups"]
        commune_group = next(group for group in flow_groups if group["flow"] == SankeyFlow.COMMUNE)
        rendered_category = next(c for c in commune_group["categories"] if c.pk == category.pk)
        assert rendered_category.nature_range_rules_for_scheme == [mch1_rule]
        assert len(rendered_category.function_nature_rules_for_scheme) == 1


class TestSankeyRuleCreateView:
    @pytest.mark.parametrize("scheme", ChartScheme.values)
    @pytest.mark.parametrize("sub_account", ["", "01"])
    @pytest.mark.parametrize("same_category", [False, True])
    def test_duplicate_exact_code_returns_its_category_and_preserves_input(
        self, client, scheme, sub_account, same_category
    ):
        user = UserFactory()
        _grant_change_sankey_category(user)
        client.force_login(user)
        existing_category = _make_category(name="Existing category")
        data = {**EXACT_CODE_INPUT, "sub_account": sub_account}
        existing = SankeyAccountCodeRuleFactory(scheme=scheme, category=existing_category, **data)
        target = existing_category if same_category else _make_category()

        response = client.post(
            reverse("finance:sankey-rule-add", args=["account-code", target.pk]),
            data,
            QUERY_STRING=f"scheme={scheme}",
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == HTTPStatus.OK
        assert "HX-Trigger" not in response
        form = response.context["form"]
        assert form.non_field_errors().as_data()[0].code == DUPLICATE_EXACT_CODE_ERROR
        assert form.conflicting_rule == existing
        assert {field: form[field].value() for field in data} == data
        html = response.content.decode()
        assert existing_category.name in html
        assert scheme.upper() in html
        assert reverse("finance:sankey-rule-edit", args=["account-code", existing.pk]) in html
        assert SankeyAccountCodeRule.objects.filter(scheme=scheme, **data).count() == 1
        existing.refresh_from_db()
        assert existing.category_id == existing_category.pk

    def test_exact_code_in_another_scheme_is_allowed(self, client):
        user = UserFactory()
        _grant_change_sankey_category(user)
        client.force_login(user)
        SankeyAccountCodeRuleFactory(scheme=ChartScheme.MCH1, **EXACT_CODE_INPUT)
        category = _make_category()

        response = client.post(
            reverse("finance:sankey-rule-add", args=["account-code", category.pk]),
            EXACT_CODE_INPUT,
            QUERY_STRING=f"scheme={ChartScheme.MCH2}",
        )

        assert response.status_code == HTTPStatus.OK
        assert response["HX-Trigger"] == "closeSankeyRuleModal"
        assert (
            SankeyAccountCodeRule.objects.get(scheme=ChartScheme.MCH2, **EXACT_CODE_INPUT).category_id == category.pk
        )

    def test_missing_fields_do_not_trigger_duplicate_lookup(self, client):
        user = UserFactory()
        _grant_change_sankey_category(user)
        client.force_login(user)
        category = _make_category()

        response = client.post(
            reverse("finance:sankey-rule-add", args=["account-code", category.pk]),
            {"nature": "4472"},
            QUERY_STRING=f"scheme={ChartScheme.MCH2}",
        )

        assert response.status_code == HTTPStatus.OK
        assert "function" in response.context["form"].errors
        assert not response.context["form"].non_field_errors()

    def test_concurrent_duplicate_is_reported_after_savepoint_rollback(self, client, monkeypatch):
        user = UserFactory()
        _grant_change_sankey_category(user)
        client.force_login(user)
        existing = SankeyAccountCodeRuleFactory(scheme=ChartScheme.MCH2, **EXACT_CODE_INPUT)
        category = _make_category()
        # The initial validation misses the other transaction's insert. The
        # database really raises IntegrityError when this request tries to save.
        lookups = iter([None, existing])
        monkeypatch.setattr(SankeyAccountCodeRuleForm, "find_conflicting_rule", lambda self: next(lookups))

        response = client.post(
            reverse("finance:sankey-rule-add", args=["account-code", category.pk]),
            EXACT_CODE_INPUT,
            QUERY_STRING=f"scheme={ChartScheme.MCH2}",
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == HTTPStatus.OK
        assert response.context["form"].conflicting_rule == existing
        assert "HX-Trigger" not in response
        assert SankeyAccountCodeRule.objects.filter(scheme=ChartScheme.MCH2, **EXACT_CODE_INPUT).count() == 1

    def test_unrelated_integrity_error_is_not_swallowed(self, client, monkeypatch):
        user = UserFactory()
        _grant_change_sankey_category(user)
        client.force_login(user)
        category = _make_category()

        def fail_save(self):
            message = "Unrelated failure"
            raise IntegrityError(message)

        monkeypatch.setattr(SankeyAccountCodeRuleForm, "save", fail_save)
        with pytest.raises(IntegrityError, match="Unrelated failure"):
            client.post(
                reverse("finance:sankey-rule-add", args=["account-code", category.pk]),
                EXACT_CODE_INPUT,
                QUERY_STRING=f"scheme={ChartScheme.MCH2}",
            )

    def test_invalid_scheme_cannot_create_rule(self, client):
        user = UserFactory()
        _grant_change_sankey_category(user)
        client.force_login(user)
        category = _make_category()

        response = client.post(
            reverse("finance:sankey-rule-add", args=["nature-range", category.pk]),
            {"nature_start": 9500, "nature_end": 9509, "priority": 100},
            QUERY_STRING="scheme=invalid",
        )

        assert response.status_code == HTTPStatus.NOT_FOUND
        assert not SankeyNatureRangeRule.objects.filter(category=category).exists()

    def test_login_required(self, client):
        category = _make_category()
        response = client.get(reverse("finance:sankey-rule-add", args=["nature-range", category.pk]))
        assert response.status_code == HTTPStatus.FOUND
        assert LOGIN_URL in response.url

    def test_view_only_permission_is_forbidden(self, client):
        user = UserFactory()
        _grant_view_sankey_category(user)
        client.force_login(user)
        category = _make_category()

        response = client.get(reverse("finance:sankey-rule-add", args=["nature-range", category.pk]))

        assert response.status_code == HTTPStatus.FORBIDDEN

    def test_get_returns_blank_form(self, client):
        user = UserFactory()
        _grant_change_sankey_category(user)
        client.force_login(user)
        category = _make_category()

        response = client.get(reverse("finance:sankey-rule-add", args=["nature-range", category.pk]))

        assert response.status_code == HTTPStatus.OK

    def test_post_creates_rule_and_returns_oob_rows(self, client):
        user = UserFactory()
        _grant_change_sankey_category(user)
        client.force_login(user)
        category = _make_category()

        nature_start, nature_end = 9500, 9509
        response = client.post(
            reverse("finance:sankey-rule-add", args=["nature-range", category.pk]),
            {"nature_start": nature_start, "nature_end": nature_end, "priority": 100},
            QUERY_STRING=f"scheme={ChartScheme.MCH2}",
        )

        assert response.status_code == HTTPStatus.OK
        assert response["HX-Trigger"] == "closeSankeyRuleModal"
        rule = SankeyNatureRangeRule.objects.get(scheme=ChartScheme.MCH2, category=category)
        assert rule.nature_start == nature_start
        assert rule.nature_end == nature_end
        assert f'id="rules-nature-range-{category.pk}"' in response.content.decode()

    def test_unknown_rule_type_is_not_found(self, client):
        user = UserFactory()
        _grant_change_sankey_category(user)
        client.force_login(user)
        category = _make_category()

        response = client.get(reverse("finance:sankey-rule-add", args=["not-a-rule-type", category.pk]))

        assert response.status_code == HTTPStatus.NOT_FOUND


class TestSankeyRuleUpdateView:
    @pytest.mark.parametrize("scheme", ChartScheme.values)
    def test_duplicate_exact_code_is_reported_without_changing_either_rule(self, client, scheme):
        user = UserFactory()
        _grant_change_sankey_category(user)
        client.force_login(user)
        existing = SankeyAccountCodeRuleFactory(scheme=scheme, **EXACT_CODE_INPUT)
        rule = SankeyAccountCodeRuleFactory(scheme=scheme, **{**EXACT_CODE_INPUT, "function": "02905"})
        original_function = rule.function

        response = client.post(
            reverse("finance:sankey-rule-edit", args=["account-code", rule.pk]),
            EXACT_CODE_INPUT,
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == HTTPStatus.OK
        assert response.context["form"].conflicting_rule == existing
        assert "HX-Trigger" not in response
        rule.refresh_from_db()
        assert rule.function == original_function
        assert SankeyAccountCodeRule.objects.filter(scheme=scheme, **EXACT_CODE_INPUT).count() == 1

    def test_unchanged_exact_code_does_not_conflict_with_itself(self, client):
        user = UserFactory()
        _grant_change_sankey_category(user)
        client.force_login(user)
        rule = SankeyAccountCodeRuleFactory(scheme=ChartScheme.MCH2, **EXACT_CODE_INPUT)

        response = client.post(
            reverse("finance:sankey-rule-edit", args=["account-code", rule.pk]),
            EXACT_CODE_INPUT,
        )

        assert response.status_code == HTTPStatus.OK
        assert response["HX-Trigger"] == "closeSankeyRuleModal"

    def test_concurrent_duplicate_during_edit_preserves_original_rule(self, client, monkeypatch):
        user = UserFactory()
        _grant_change_sankey_category(user)
        client.force_login(user)
        existing = SankeyAccountCodeRuleFactory(scheme=ChartScheme.MCH2, **EXACT_CODE_INPUT)
        rule = SankeyAccountCodeRuleFactory(scheme=ChartScheme.MCH2, **{**EXACT_CODE_INPUT, "function": "02905"})
        original_function = rule.function
        lookups = iter([None, existing])
        monkeypatch.setattr(SankeyAccountCodeRuleForm, "find_conflicting_rule", lambda self: next(lookups))

        response = client.post(
            reverse("finance:sankey-rule-edit", args=["account-code", rule.pk]),
            EXACT_CODE_INPUT,
        )

        assert response.status_code == HTTPStatus.OK
        assert response.context["form"].conflicting_rule == existing
        rule.refresh_from_db()
        assert rule.function == original_function

    def test_login_required(self, client):
        rule = _make_nature_range_rule()
        response = client.get(reverse("finance:sankey-rule-edit", args=["nature-range", rule.pk]))
        assert response.status_code == HTTPStatus.FOUND
        assert LOGIN_URL in response.url

    def test_wrong_scheme_cannot_update_rule(self, client):
        user = UserFactory()
        _grant_change_sankey_category(user)
        client.force_login(user)
        rule = _make_nature_range_rule(scheme=ChartScheme.MCH1)
        original_nature_end = rule.nature_end

        response = client.post(
            reverse("finance:sankey-rule-edit", args=["nature-range", rule.pk]),
            {"nature_start": 9000, "nature_end": 9099, "priority": 150},
            QUERY_STRING=f"scheme={ChartScheme.MCH2}",
        )

        assert response.status_code == HTTPStatus.NOT_FOUND
        rule.refresh_from_db()
        assert rule.nature_end == original_nature_end

    def test_view_only_permission_is_forbidden(self, client):
        user = UserFactory()
        _grant_view_sankey_category(user)
        client.force_login(user)
        rule = _make_nature_range_rule()

        response = client.get(reverse("finance:sankey-rule-edit", args=["nature-range", rule.pk]))

        assert response.status_code == HTTPStatus.FORBIDDEN

    def test_post_updates_rule_and_returns_oob_rows(self, client):
        user = UserFactory()
        _grant_change_sankey_category(user)
        client.force_login(user)
        new_nature_end, new_priority = 9099, 150
        rule = _make_nature_range_rule(nature_start=9000, nature_end=9009, priority=100)

        response = client.post(
            reverse("finance:sankey-rule-edit", args=["nature-range", rule.pk]),
            {"nature_start": 9000, "nature_end": new_nature_end, "priority": new_priority},
        )

        assert response.status_code == HTTPStatus.OK
        assert response["HX-Trigger"] == "closeSankeyRuleModal"
        rule.refresh_from_db()
        assert rule.nature_end == new_nature_end
        assert rule.priority == new_priority
        assert str(new_priority) in response.content.decode()


class TestSankeyRuleDeleteView:
    def test_login_required(self, client, sankey_rule_case):
        kind, rule = sankey_rule_case
        response = client.get(reverse("finance:sankey-rule-delete", args=[kind, rule.pk]))
        assert response.status_code == HTTPStatus.FOUND
        assert LOGIN_URL in response.url

    @pytest.mark.parametrize("method", ["get", "post"])
    def test_view_only_permission_is_forbidden(self, client, sankey_rule_case, method):
        kind, rule = sankey_rule_case
        user = UserFactory()
        _grant_view_sankey_category(user)
        client.force_login(user)

        response = getattr(client, method)(reverse("finance:sankey-rule-delete", args=[kind, rule.pk]))

        assert response.status_code == HTTPStatus.FORBIDDEN
        assert type(rule).objects.filter(pk=rule.pk).exists()

    def test_get_confirms_without_deleting(self, client, sankey_rule_case):
        kind, rule = sankey_rule_case
        user = UserFactory()
        _grant_change_sankey_category(user)
        client.force_login(user)

        response = client.get(reverse("finance:sankey-rule-delete", args=[kind, rule.pk]))

        assert response.status_code == HTTPStatus.OK
        assert response.context["scheme"] == rule.scheme
        assert gettext("Delete rule") in response.content.decode()
        assert 'name="csrfmiddlewaretoken"' in response.content.decode()
        assert type(rule).objects.filter(pk=rule.pk).exists()

    def test_post_deletes_only_the_selected_rule_and_refreshes_empty_state(self, client, sankey_rule_case):
        kind, rule = sankey_rule_case
        user = UserFactory()
        _grant_change_sankey_category(user)
        client.force_login(user)
        other_scheme = ChartScheme.MCH2 if rule.scheme == ChartScheme.MCH1 else ChartScheme.MCH1
        other = RULE_FACTORIES[kind](category=rule.category, scheme=other_scheme)
        account = AccountFactory(charges=Decimal("123"), revenues=Decimal("45"))
        before_account = type(account).objects.values().get(pk=account.pk)
        category = rule.category
        rule_pk = rule.pk

        response = client.post(
            reverse("finance:sankey-rule-delete", args=[kind, rule.pk]),
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == HTTPStatus.OK
        assert response["HX-Trigger"] == "closeSankeyRuleModal"
        assert not type(rule).objects.filter(pk=rule_pk).exists()
        assert type(other).objects.filter(pk=other.pk).exists()
        assert SankeyCategory.objects.filter(pk=category.pk).exists()
        assert type(account).objects.values().get(pk=account.pk) == before_account
        html = response.content.decode()
        assert f'id="rules-{kind}-{category.pk}"' in html
        assert 'hx-swap-oob="true"' in html
        assert gettext("No rule for this scheme yet.") in html

    def test_wrong_scheme_is_not_deleted(self, client, sankey_rule_case):
        kind, rule = sankey_rule_case
        user = UserFactory()
        _grant_change_sankey_category(user)
        client.force_login(user)
        other_scheme = ChartScheme.MCH2 if rule.scheme == ChartScheme.MCH1 else ChartScheme.MCH1

        response = client.post(
            reverse("finance:sankey-rule-delete", args=[kind, rule.pk]),
            QUERY_STRING=f"scheme={other_scheme}",
        )

        assert response.status_code == HTTPStatus.NOT_FOUND
        assert type(rule).objects.filter(pk=rule.pk).exists()

    def test_post_requires_csrf(self, sankey_rule_case):
        kind, rule = sankey_rule_case
        user = UserFactory()
        _grant_change_sankey_category(user)
        client = Client(enforce_csrf_checks=True)
        client.force_login(user)

        response = client.post(reverse("finance:sankey-rule-delete", args=[kind, rule.pk]))

        assert response.status_code == HTTPStatus.FORBIDDEN
        assert type(rule).objects.filter(pk=rule.pk).exists()

    def test_plain_post_redirects_to_actual_scheme(self, client, sankey_rule_case):
        kind, rule = sankey_rule_case
        user = UserFactory()
        _grant_change_sankey_category(user)
        client.force_login(user)

        response = client.post(reverse("finance:sankey-rule-delete", args=[kind, rule.pk]))

        assert response.status_code == HTTPStatus.FOUND
        assert response.url == (
            f"{reverse('finance:sankey-rules')}?scheme={rule.scheme}#sankey-category-{rule.category_id}"
        )

    def test_unknown_rule_type_is_not_found(self, client):
        user = UserFactory()
        _grant_change_sankey_category(user)
        client.force_login(user)

        response = client.post(reverse("finance:sankey-rule-delete", args=["invalid", 1]))

        assert response.status_code == HTTPStatus.NOT_FOUND


class TestSankeyCategoryEditView:
    def test_duplicate_name_identifies_existing_group_and_preserves_both_categories(self, client):
        user = UserFactory()
        _grant_change_sankey_category(user)
        client.force_login(user)
        existing = _make_category(name=DUPLICATE_CATEGORY_NAME, flow=SankeyFlow.REVENUE)
        category = _make_category(name="Other category", flow=SankeyFlow.COMMUNE)
        original_name = category.name

        response = client.post(
            reverse("finance:sankey-category-edit", args=[category.pk]),
            {"name": existing.name, "color": "#224466", "order": 0},
            QUERY_STRING=f"scheme={ChartScheme.MCH2}",
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == HTTPStatus.OK
        form = response.context["form"]
        assert form.conflicting_category == existing
        assert form.errors.as_data()["name"][0].code == DUPLICATE_CATEGORY_ERROR
        assert existing.get_flow_display() in response.content.decode()
        assert "HX-Trigger" not in response
        category.refresh_from_db()
        assert category.name == original_name

    def test_concurrent_duplicate_name_during_edit_rolls_back(self, client, monkeypatch):
        user = UserFactory()
        _grant_change_sankey_category(user)
        client.force_login(user)
        existing = _make_category(name=DUPLICATE_CATEGORY_NAME)
        category = _make_category(name="Other category")
        original_name = category.name
        lookups = iter([None, existing])
        monkeypatch.setattr(SankeyCategoryForm, "find_conflicting_category", lambda self: next(lookups))

        response = client.post(
            reverse("finance:sankey-category-edit", args=[category.pk]),
            {"name": existing.name, "color": "#224466", "order": 0},
        )

        assert response.status_code == HTTPStatus.OK
        assert response.context["form"].conflicting_category == existing
        category.refresh_from_db()
        assert category.name == original_name

    def test_view_only_permission_is_forbidden(self, client):
        user = UserFactory()
        _grant_view_sankey_category(user)
        client.force_login(user)
        category = _make_category()

        response = client.get(reverse("finance:sankey-category-edit", args=[category.pk]))

        assert response.status_code == HTTPStatus.FORBIDDEN

    def test_post_updates_category_and_returns_oob_header(self, client):
        user = UserFactory()
        _grant_change_sankey_category(user)
        client.force_login(user)
        category = _make_category(name="Old name", color="#111111", order=0)

        response = client.post(
            reverse("finance:sankey-category-edit", args=[category.pk]),
            {"name": "New name", "color": "#222222", "order": 1},
        )

        assert response.status_code == HTTPStatus.OK
        assert response["HX-Trigger"] == "closeSankeyRuleModal"
        category.refresh_from_db()
        assert category.name == "New name"
        assert category.color == "#222222"
        assert f'id="category-header-{category.pk}"' in response.content.decode()


class TestSankeyDataView:
    def test_login_required(self, client):
        response = client.get(reverse("finance:data_buckets"), {"year": 2025})
        assert response.status_code == HTTPStatus.FOUND
        assert LOGIN_URL in response.url

    def test_missing_year_returns_400(self, client):
        client.force_login(UserFactory())
        response = client.get(reverse("finance:data_buckets"))
        assert response.status_code == HTTPStatus.BAD_REQUEST

    def test_returns_nodes_and_links(self, client):
        client.force_login(UserFactory())
        category = SankeyCategoryFactory(name="Impots", flow=SankeyFlow.REVENUE)
        SankeyAccountCodeRuleFactory(scheme=ChartScheme.MCH1, function="100", nature="400", category=category)
        AccountFactory.create(
            function="100", nature="400", revenues=Decimal("1000.00"), scheme=ChartScheme.MCH1, year=2025
        )

        response = client.get(reverse("finance:data_buckets"), {"year": 2025})

        assert response.status_code == HTTPStatus.OK
        data = response.json()
        assert "nodes" in data
        assert "links" in data


class TestSankeyMaticExportView:
    def test_login_required(self, client):
        response = client.get(reverse("finance:sankeymatic_export"), {"year": 2025})
        assert response.status_code == HTTPStatus.FOUND
        assert LOGIN_URL in response.url

    def test_missing_year_returns_400(self, client):
        client.force_login(UserFactory())
        response = client.get(reverse("finance:sankeymatic_export"))
        assert response.status_code == HTTPStatus.BAD_REQUEST

    def test_returns_downloadable_text_file(self, client):
        client.force_login(UserFactory())
        category = SankeyCategoryFactory(name="Impots", flow=SankeyFlow.REVENUE)
        SankeyAccountCodeRuleFactory(scheme=ChartScheme.MCH1, function="100", nature="400", category=category)
        AccountFactory.create(
            function="100", nature="400", revenues=Decimal("1000.00"), scheme=ChartScheme.MCH1, year=2025
        )

        response = client.get(reverse("finance:sankeymatic_export"), {"year": 2025})

        assert response.status_code == HTTPStatus.OK
        assert response["Content-Type"] == "text/plain; charset=utf-8"
        assert "attachment" in response["Content-Disposition"]


class TestSankeyCategoryCreateView:
    @pytest.mark.parametrize("scheme", ChartScheme.values)
    @pytest.mark.parametrize("flow", SankeyFlow.values)
    def test_duplicate_name_identifies_shared_category_even_without_rules(self, client, scheme, flow):
        user = UserFactory()
        _grant_change_sankey_category(user)
        client.force_login(user)
        existing = _make_category(name=DUPLICATE_CATEGORY_NAME, flow=flow)
        before = SankeyCategory.objects.values().get(pk=existing.pk)
        target_flow = SankeyFlow.COMMUNE if flow == SankeyFlow.REVENUE else SankeyFlow.REVENUE

        response = client.post(
            reverse("finance:sankey-category-add"),
            {"name": existing.name, "flow": target_flow, "color": "#224466", "order": 0},
            QUERY_STRING=f"scheme={scheme}",
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == HTTPStatus.OK
        form = response.context["form"]
        assert form.conflicting_category == existing
        assert form.errors.as_data()["name"][0].code == DUPLICATE_CATEGORY_ERROR
        assert form["name"].value() == existing.name
        html = response.content.decode()
        assert existing.get_flow_display() in html
        assert "MCH1" in html
        assert "MCH2" in html
        assert reverse("finance:sankey-category-edit", args=[existing.pk]) in html
        assert "HX-Redirect" not in response
        assert "HX-Refresh" not in response
        assert SankeyCategory.objects.values().get(pk=existing.pk) == before
        assert SankeyCategory.objects.filter(name=existing.name).count() == 1

    def test_concurrent_duplicate_category_returns_the_existing_location(self, client, monkeypatch):
        user = UserFactory()
        _grant_change_sankey_category(user)
        client.force_login(user)
        existing = _make_category(name=DUPLICATE_CATEGORY_NAME, flow=SankeyFlow.REVENUE)
        lookups = iter([None, existing])
        monkeypatch.setattr(SankeyCategoryForm, "find_conflicting_category", lambda self: next(lookups))

        response = client.post(
            reverse("finance:sankey-category-add"),
            {"name": existing.name, "flow": SankeyFlow.COMMUNE, "color": "#224466", "order": 0},
            QUERY_STRING=f"scheme={ChartScheme.MCH2}",
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == HTTPStatus.OK
        assert response.context["form"].conflicting_category == existing
        assert "HX-Redirect" not in response
        assert SankeyCategory.objects.filter(name=existing.name).count() == 1

    def test_login_required(self, client):
        response = client.get(reverse("finance:sankey-category-add"))
        assert response.status_code == HTTPStatus.FOUND
        assert LOGIN_URL in response.url

    @pytest.mark.parametrize("method", ["get", "post"])
    def test_view_permission_does_not_allow_creation(self, client, method):
        user = UserFactory()
        _grant_view_sankey_category(user)
        client.force_login(user)
        response = getattr(client, method)(reverse("finance:sankey-category-add"))
        assert response.status_code == HTTPStatus.FORBIDDEN

    def test_get_prefills_group_and_shows_shared_category_help(self, client):
        user = UserFactory()
        _grant_change_sankey_category(user)
        client.force_login(user)
        response = client.get(reverse("finance:sankey-category-add"), {"flow": SankeyFlow.INTERCOMMUNALITY})
        assert response.status_code == HTTPStatus.OK
        assert response.context["form"].initial["flow"] == SankeyFlow.INTERCOMMUNALITY
        assert response.context["is_create"]
        assert response.context["is_category"]

    @pytest.mark.parametrize("flow", SankeyFlow.values)
    def test_creates_category_in_each_group_and_returns_to_its_rules(self, client, flow, site_configuration_with_logo):
        user = UserFactory()
        _grant_change_sankey_category(user)
        _grant_view_sankey_category(user)
        client.force_login(user)
        url = reverse("finance:sankey-category-add") + f"?scheme={ChartScheme.MCH2}"
        response = client.post(
            url, {"name": "New interco", "flow": flow, "color": "#224466", "order": 1}, HTTP_HX_REQUEST="true"
        )
        assert response.status_code == HTTPStatus.OK
        category = SankeyCategory.objects.get(name="New interco")
        assert category.flow == flow
        assert category.color == "#224466"
        assert response["HX-Redirect"] == (
            f"{reverse('finance:sankey-rules')}?scheme={ChartScheme.MCH2}#sankey-category-{category.pk}"
        )
        assert response["HX-Refresh"] == "true"
        response = client.get(response["HX-Redirect"])
        assert f'id="sankey-category-{category.pk}"' in response.content.decode()
        assert f'id="category-nav-{category.pk}"' in response.content.decode()
        assert not category.nature_range_rules.exists()

    def test_normal_post_redirects_preserving_scheme(self, client):
        user = UserFactory()
        _grant_change_sankey_category(user)
        client.force_login(user)
        url = reverse("finance:sankey-category-add") + f"?scheme={ChartScheme.MCH1}"
        response = client.post(
            url, {"name": "New grouping", "flow": SankeyFlow.COMMUNE, "color": "#224466", "order": 0}
        )
        assert response.status_code == HTTPStatus.FOUND
        assert f"scheme={ChartScheme.MCH1}" in response.url

    @pytest.mark.parametrize(("flow", "name"), [("invalid", "New grouping"), (SankeyFlow.COMMUNE, "Existing")])
    def test_invalid_or_duplicate_category_is_not_saved(self, client, flow, name):
        existing = _make_category(name="Existing")
        user = UserFactory()
        _grant_change_sankey_category(user)
        client.force_login(user)
        response = client.post(
            reverse("finance:sankey-category-add"), {"name": name, "flow": flow, "color": "#224466", "order": 0}
        )
        assert response.status_code == HTTPStatus.OK
        assert response.context["form"].errors
        assert "HX-Redirect" not in response
        existing.refresh_from_db()
        assert existing.color != "#224466"
        assert not SankeyCategory.objects.filter(name="New grouping").exists()

    def test_create_button_requires_edit_permission(self, client, site_configuration_with_logo):
        user = UserFactory()
        _grant_view_sankey_category(user)
        client.force_login(user)
        url = reverse("finance:sankey-rules")
        create_url = reverse("finance:sankey-category-add")
        assert create_url not in client.get(url).content.decode()
        _grant_change_sankey_category(user)
        assert create_url in client.get(url).content.decode()
