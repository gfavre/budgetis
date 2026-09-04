import pytest

from budgetis.common.models import ChartScheme
from budgetis.finance.models import SankeyFlow
from budgetis.finance.tests.factories import SankeyAccountCodeRuleFactory
from budgetis.finance.tests.factories import SankeyCategoryFactory
from budgetis.finance.tests.factories import SankeyLabelRuleFactory
from budgetis.finance.tests.factories import SankeyNatureRangeRuleFactory


pytestmark = pytest.mark.django_db


class TestSankeyCategory:
    def test_str_returns_name(self):
        category = SankeyCategoryFactory.build(name="Salaires")
        assert str(category) == "Salaires"


class TestSankeyNatureRangeRule:
    def test_matches_within_range(self):
        rule = SankeyNatureRangeRuleFactory.build(nature_start=300, nature_end=309)
        assert rule.matches(300) is True
        assert rule.matches(309) is True
        assert rule.matches(305) is True

    def test_does_not_match_outside_range(self):
        rule = SankeyNatureRangeRuleFactory.build(nature_start=300, nature_end=309)
        assert rule.matches(299) is False
        assert rule.matches(310) is False

    def test_str_includes_scheme_and_range(self):
        category = SankeyCategoryFactory.build(name="Salaires")
        rule = SankeyNatureRangeRuleFactory.build(
            scheme=ChartScheme.MCH1, nature_start=300, nature_end=309, category=category
        )
        assert str(rule) == "mch1 300-309 → Salaires"


class TestSankeyAccountCodeRule:
    def test_str_without_sub_account(self):
        category = SankeyCategoryFactory.build(name="Péréquation")
        rule = SankeyAccountCodeRuleFactory.build(function="220", nature="352", sub_account="", category=category)
        assert str(rule) == "mch1 220.352 → Péréquation"

    def test_str_with_sub_account(self):
        category = SankeyCategoryFactory.build(name="RAT")
        rule = SankeyAccountCodeRuleFactory.build(function="710", nature="365", sub_account="1", category=category)
        assert str(rule) == "mch1 710.365.1 → RAT"


class TestSankeyLabelRule:
    def test_str_includes_pattern(self):
        category = SankeyCategoryFactory.build(name="AISGE", flow=SankeyFlow.INTERCOMMUNALITY)
        rule = SankeyLabelRuleFactory.build(scheme=ChartScheme.MCH2, pattern="AISGE", category=category)
        assert str(rule) == "mch2 'AISGE' → AISGE"
