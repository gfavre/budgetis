from http import HTTPStatus

import pytest
from django.urls import reverse

from budgetis.finance.tests.factories import SankeyAccountCodeRuleFactory
from budgetis.finance.tests.factories import SankeyCategoryFactory
from budgetis.finance.tests.factories import SankeyFunctionNatureRuleFactory
from budgetis.finance.tests.factories import SankeyLabelRuleFactory
from budgetis.finance.tests.factories import SankeyNatureRangeRuleFactory


pytestmark = pytest.mark.django_db


class TestSankeyCategoryAdmin:
    def test_changelist(self, admin_client):
        SankeyCategoryFactory()
        response = admin_client.get(reverse("admin:finance_sankeycategory_changelist"))
        assert response.status_code == HTTPStatus.OK


class TestSankeyNatureRangeRuleAdmin:
    def test_changelist(self, admin_client):
        SankeyNatureRangeRuleFactory()
        response = admin_client.get(reverse("admin:finance_sankeynaturerangerule_changelist"))
        assert response.status_code == HTTPStatus.OK


class TestSankeyFunctionNatureRuleAdmin:
    def test_changelist(self, admin_client):
        SankeyFunctionNatureRuleFactory()
        response = admin_client.get(reverse("admin:finance_sankeyfunctionnaturerule_changelist"))
        assert response.status_code == HTTPStatus.OK


class TestSankeyAccountCodeRuleAdmin:
    def test_changelist(self, admin_client):
        SankeyAccountCodeRuleFactory()
        response = admin_client.get(reverse("admin:finance_sankeyaccountcoderule_changelist"))
        assert response.status_code == HTTPStatus.OK


class TestSankeyLabelRuleAdmin:
    def test_changelist(self, admin_client):
        SankeyLabelRuleFactory()
        response = admin_client.get(reverse("admin:finance_sankeylabelrule_changelist"))
        assert response.status_code == HTTPStatus.OK
