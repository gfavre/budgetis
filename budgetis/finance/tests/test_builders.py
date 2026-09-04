from decimal import Decimal

import pytest

from budgetis.accounting.models import Account
from budgetis.accounting.tests.factories import AccountFactory
from budgetis.common.models import ChartScheme
from budgetis.finance.builders import LABEL_HOUSEHOLD
from budgetis.finance.builders import LABEL_PROFIT
from budgetis.finance.builders import LABEL_RESULT_HUB
from budgetis.finance.builders import build_income_budget_canton_intercos_commune
from budgetis.finance.builders import build_sankeymatic_export
from budgetis.finance.models import SankeyFlow
from budgetis.finance.tests.factories import SankeyAccountCodeRuleFactory
from budgetis.finance.tests.factories import SankeyCategoryFactory
from budgetis.finance.tests.factories import SankeyNatureRangeRuleFactory


pytestmark = pytest.mark.django_db

# Test-only codes chosen to fall outside every range/code seeded by the finance
# migrations (MCH1 up to nature 499), so a fixture's own rules are the only
# ones that ever match its accounts - see test_rules.py for the same pattern.
REVENUE_FUNCTION = "900"
REVENUE_NATURE = "9000"
COMMUNE_FUNCTION = "901"
COMMUNE_NATURE = "9011"
COMMUNE_NATURE_RANGE = (9010, 9019)


@pytest.fixture
def small_diagram_rules():
    """One revenue category and one commune (charges) category, MCH1-scoped."""
    revenue = SankeyCategoryFactory(flow=SankeyFlow.REVENUE, color="#111111")
    commune = SankeyCategoryFactory(flow=SankeyFlow.COMMUNE, color="#222222")
    SankeyAccountCodeRuleFactory(
        scheme=ChartScheme.MCH1, function=REVENUE_FUNCTION, nature=REVENUE_NATURE, category=revenue
    )
    SankeyNatureRangeRuleFactory(
        scheme=ChartScheme.MCH1,
        nature_start=COMMUNE_NATURE_RANGE[0],
        nature_end=COMMUNE_NATURE_RANGE[1],
        category=commune,
    )
    return revenue, commune


def _node_for(data, category) -> dict:
    return next(n for n in data["nodes"] if category.name in n["name"])


class TestBuildIncomeBudgetCantonIntercosCommune:
    def test_leaf_node_value_reflects_account_totals(self, small_diagram_rules):
        revenue, _commune = small_diagram_rules
        AccountFactory.create(
            function=REVENUE_FUNCTION,
            nature=REVENUE_NATURE,
            revenues=Decimal("1000.00"),
            charges=Decimal("0.00"),
            scheme=ChartScheme.MCH1,
        )
        qs = Account.objects.filter(function=REVENUE_FUNCTION)

        data = build_income_budget_canton_intercos_commune(qs, ChartScheme.MCH1)

        assert "CHF1.00K" in _node_for(data, revenue)["name"]

    def test_balanced_flow_has_no_result_node(self, small_diagram_rules):
        AccountFactory.create(
            function=REVENUE_FUNCTION,
            nature=REVENUE_NATURE,
            revenues=Decimal("1000.00"),
            charges=Decimal("0.00"),
            scheme=ChartScheme.MCH1,
        )
        AccountFactory.create(
            function=COMMUNE_FUNCTION,
            nature=COMMUNE_NATURE,
            charges=Decimal("1000.00"),
            revenues=Decimal("0.00"),
            scheme=ChartScheme.MCH1,
        )
        qs = Account.objects.filter(function__in=[REVENUE_FUNCTION, COMMUNE_FUNCTION])

        data = build_income_budget_canton_intercos_commune(qs, ChartScheme.MCH1)

        node_names = [n["name"] for n in data["nodes"]]
        assert not any(str(LABEL_RESULT_HUB) in name for name in node_names)

    def test_surplus_creates_a_result_and_profit_node(self, small_diagram_rules):
        AccountFactory.create(
            function=REVENUE_FUNCTION,
            nature=REVENUE_NATURE,
            revenues=Decimal("1000.00"),
            charges=Decimal("0.00"),
            scheme=ChartScheme.MCH1,
        )
        AccountFactory.create(
            function=COMMUNE_FUNCTION,
            nature=COMMUNE_NATURE,
            charges=Decimal("400.00"),
            revenues=Decimal("0.00"),
            scheme=ChartScheme.MCH1,
        )
        qs = Account.objects.filter(function__in=[REVENUE_FUNCTION, COMMUNE_FUNCTION])

        data = build_income_budget_canton_intercos_commune(qs, ChartScheme.MCH1)

        node_names = [n["name"] for n in data["nodes"]]
        assert any(str(LABEL_RESULT_HUB) in name for name in node_names)
        assert any(str(LABEL_PROFIT) in name for name in node_names)

    def test_dotations_link_directly_from_household(self):
        dotation = SankeyCategoryFactory(flow=SankeyFlow.DOTATION, color="#333333")
        SankeyNatureRangeRuleFactory(scheme=ChartScheme.MCH1, nature_start=9020, nature_end=9029, category=dotation)
        AccountFactory.create(
            function="902", nature="9021", charges=Decimal("200.00"), revenues=Decimal("0.00"), scheme=ChartScheme.MCH1
        )
        qs = Account.objects.filter(function="902")

        data = build_income_budget_canton_intercos_commune(qs, ChartScheme.MCH1)

        dotation_node_index = next(i for i, n in enumerate(data["nodes"]) if dotation.name in n["name"])
        household_node_index = next(i for i, n in enumerate(data["nodes"]) if str(LABEL_HOUSEHOLD) in n["name"])
        dotation_link = next(link for link in data["links"] if link["target"] == dotation_node_index)
        assert dotation_link["source"] == household_node_index


class TestBuildSankeymaticExport:
    def test_uses_french_labels_regardless_of_active_language(self, small_diagram_rules):
        AccountFactory.create(
            function=REVENUE_FUNCTION,
            nature=REVENUE_NATURE,
            revenues=Decimal("1000.00"),
            charges=Decimal("0.00"),
            scheme=ChartScheme.MCH1,
        )
        AccountFactory.create(
            function=COMMUNE_FUNCTION,
            nature=COMMUNE_NATURE,
            charges=Decimal("400.00"),
            revenues=Decimal("0.00"),
            scheme=ChartScheme.MCH1,
        )
        qs = Account.objects.filter(function__in=[REVENUE_FUNCTION, COMMUNE_FUNCTION])

        text = build_sankeymatic_export(qs, 2025, ChartScheme.MCH1, is_budget=False)

        assert "Ménage communal" in text
        assert "Bénéfice" in text
        assert "Municipal household" not in text
        assert "Profit" not in text

    def test_deficit_shows_loss_line(self, small_diagram_rules):
        AccountFactory.create(
            function=REVENUE_FUNCTION,
            nature=REVENUE_NATURE,
            revenues=Decimal("400.00"),
            charges=Decimal("0.00"),
            scheme=ChartScheme.MCH1,
        )
        AccountFactory.create(
            function=COMMUNE_FUNCTION,
            nature=COMMUNE_NATURE,
            charges=Decimal("1000.00"),
            revenues=Decimal("0.00"),
            scheme=ChartScheme.MCH1,
        )
        qs = Account.objects.filter(function__in=[REVENUE_FUNCTION, COMMUNE_FUNCTION])

        text = build_sankeymatic_export(qs, 2025, ChartScheme.MCH1, is_budget=False)

        assert "Perte" in text
