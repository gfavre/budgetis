from decimal import Decimal
from http import HTTPStatus
from typing import cast

import pytest
from django.contrib.auth.models import Permission
from django.urls import reverse

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
from budgetis.finance.tests.factories import SankeyNatureRangeRuleFactory
from budgetis.users.tests.factories import UserFactory


pytestmark = pytest.mark.django_db

LOGIN_URL = "/accounts/login/"


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


class TestSankeyRulesView:
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
