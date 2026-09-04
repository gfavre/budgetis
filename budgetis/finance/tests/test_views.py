from decimal import Decimal
from http import HTTPStatus

import pytest
from django.urls import reverse

from budgetis.accounting.tests.factories import AccountFactory
from budgetis.common.models import ChartScheme
from budgetis.finance.models import SankeyFlow
from budgetis.finance.tests.factories import SankeyAccountCodeRuleFactory
from budgetis.finance.tests.factories import SankeyCategoryFactory
from budgetis.users.tests.factories import UserFactory


pytestmark = pytest.mark.django_db

LOGIN_URL = "/accounts/login/"


class TestSankeyView:
    def test_login_required(self, client):
        response = client.get(reverse("finance:index"))
        assert response.status_code == HTTPStatus.FOUND
        assert LOGIN_URL in response.url

    def test_authenticated_returns_200(self, client, site_configuration_with_logo):
        client.force_login(UserFactory())
        response = client.get(reverse("finance:index"))
        assert response.status_code == HTTPStatus.OK


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
