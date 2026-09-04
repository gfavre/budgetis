import factory
from factory.django import DjangoModelFactory

from budgetis.common.models import ChartScheme
from budgetis.finance.models import SankeyAccountCodeRule
from budgetis.finance.models import SankeyCategory
from budgetis.finance.models import SankeyFlow
from budgetis.finance.models import SankeyFunctionNatureRule
from budgetis.finance.models import SankeyLabelRule
from budgetis.finance.models import SankeyNatureRangeRule


class SankeyCategoryFactory(DjangoModelFactory):
    name = factory.Sequence(lambda n: f"Category {n}")
    flow = SankeyFlow.COMMUNE
    color = "#123456"
    order = 0

    class Meta:
        model = SankeyCategory


class SankeyNatureRangeRuleFactory(DjangoModelFactory):
    """
    Defaults to nature 9000-9009 - well outside any real MCH1 (up to 499) or
    MCH2 (up to 4699) code seeded by the finance migrations, so tests never
    collide with production data loaded into the test database.
    """

    scheme = ChartScheme.MCH1
    nature_start = 9000
    nature_end = 9009
    priority = 100
    category = factory.SubFactory(SankeyCategoryFactory)

    class Meta:
        model = SankeyNatureRangeRule


class SankeyAccountCodeRuleFactory(DjangoModelFactory):
    """Defaults to function/nature "900"/"9000" - see SankeyNatureRangeRuleFactory."""

    scheme = ChartScheme.MCH1
    function = "900"
    nature = "9000"
    sub_account = ""
    category = factory.SubFactory(SankeyCategoryFactory)

    class Meta:
        model = SankeyAccountCodeRule


class SankeyFunctionNatureRuleFactory(DjangoModelFactory):
    """Defaults to function prefix "90" / nature 9000-9009 - see SankeyNatureRangeRuleFactory."""

    scheme = ChartScheme.MCH1
    function_prefix = "90"
    nature_start = 9000
    nature_end = 9009
    category = factory.SubFactory(SankeyCategoryFactory)

    class Meta:
        model = SankeyFunctionNatureRule


class SankeyLabelRuleFactory(DjangoModelFactory):
    scheme = ChartScheme.MCH1
    pattern = "AISGE"
    category = factory.SubFactory(SankeyCategoryFactory)

    class Meta:
        model = SankeyLabelRule
