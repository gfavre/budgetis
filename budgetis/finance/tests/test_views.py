from decimal import Decimal
from http import HTTPStatus
from typing import cast

import pytest
from django.contrib.auth.models import Permission
from django.test import Client
from django.urls import reverse
from django.utils.translation import gettext

from budgetis.accounting.tests.factories import AccountFactory
from budgetis.accounting.tests.factories import AvailableYearFactory
from budgetis.common.models import ChartScheme
from budgetis.finance.models import AvailableYear
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
