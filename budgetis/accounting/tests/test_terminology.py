import pytest
from django.template import Context
from django.template import Template
from django.utils import translation

from budgetis.accounting.templatetags.terminology import ACCOUNTS_BY_FUNCTION
from budgetis.accounting.templatetags.terminology import OPERATING_ACCOUNT
from budgetis.accounting.templatetags.terminology import chart_term
from budgetis.accounting.tests.factories import AvailableYearFactory
from budgetis.common.models import ChartScheme
from budgetis.finance.models import AvailableYear


pytestmark = pytest.mark.django_db

MCH1_YEAR = 2026
MCH2_YEAR = 2027


@pytest.fixture
def years():
    AvailableYearFactory(year=MCH1_YEAR, type=AvailableYear.YearType.BUDGET, scheme=ChartScheme.MCH1)
    AvailableYearFactory(year=MCH2_YEAR, type=AvailableYear.YearType.BUDGET, scheme=ChartScheme.MCH2)


@pytest.mark.usefixtures("years")
class TestChartTerm:
    @pytest.mark.parametrize(
        ("term", "year", "expected"),
        [
            (OPERATING_ACCOUNT, MCH1_YEAR, "Compte de fonctionnement"),
            (OPERATING_ACCOUNT, MCH2_YEAR, "Compte de résultats"),
            (ACCOUNTS_BY_FUNCTION, MCH1_YEAR, "Comptes par fonction administrative"),
            (ACCOUNTS_BY_FUNCTION, MCH2_YEAR, "Comptes par classification fonctionnelle"),
        ],
    )
    def test_wording_follows_the_year_scheme(self, term, year, expected):
        with translation.override("fr"):
            assert str(chart_term(term, year)) == expected

    def test_unknown_year_falls_back_to_mch1(self):
        with translation.override("fr"):
            assert str(chart_term(OPERATING_ACCOUNT, 1999)) == "Compte de fonctionnement"

    def test_renders_in_a_template(self):
        template = Template('{% load terminology %}{% chart_term "operating_account" year %}')
        with translation.override("fr"):
            assert template.render(Context({"year": MCH2_YEAR})) == "Compte de résultats"
