from decimal import Decimal

import factory
from factory.django import DjangoModelFactory

from budgetis.accounting.models import Account
from budgetis.accounting.models import AccountBalanceTransfer
from budgetis.accounting.models import AccountCodeMapping
from budgetis.accounting.models import AccountComment
from budgetis.accounting.models import AccountGroup
from budgetis.accounting.models import FunctionCategory
from budgetis.accounting.models import FunctionSplit
from budgetis.accounting.models import GroupResponsibility
from budgetis.accounting.models import NatureGroup
from budgetis.common.models import ChartScheme
from budgetis.finance.models import AvailableYear
from budgetis.users.tests.factories import UserFactory


class AccountGroupFactory(DjangoModelFactory):
    """
    Defaults to a standalone MCH1 leaf group (level 3, no parent) — the shape
    most tests need. Build a full tree explicitly when a test cares about the
    hierarchy, e.g.:
        root = AccountGroupFactory(level=1, parent=None)
        mid = AccountGroupFactory(level=2, parent=root)
        leaf = AccountGroupFactory(level=3, parent=mid)
    """

    code = factory.Sequence(lambda n: str(500 + n))
    label = factory.Faker("word")
    scheme = ChartScheme.MCH1
    level = 3
    parent = None

    class Meta:
        model = AccountGroup


class FunctionSplitFactory(DjangoModelFactory):
    group = factory.SubFactory(AccountGroupFactory, scheme=ChartScheme.MCH2, level=4, code="9630")
    enabled = True

    class Meta:
        model = FunctionSplit


class FunctionCategoryFactory(DjangoModelFactory):
    split = factory.SubFactory(FunctionSplitFactory)
    function = "96301"
    label = "Maison gothique"

    class Meta:
        model = FunctionCategory


class NatureGroupFactory(DjangoModelFactory):
    code = factory.Sequence(lambda n: str(300 + n))
    label = factory.Faker("word")
    scheme = ChartScheme.MCH2
    level = 2
    parent = None

    class Meta:
        model = NatureGroup


class AccountFactory(DjangoModelFactory):
    year = 2024
    function = factory.Sequence(lambda n: str(500 + n))
    nature = factory.Sequence(lambda n: str(350 + n))
    sub_account = ""
    label = factory.Faker("word")
    group = factory.SubFactory(AccountGroupFactory)
    is_budget = False
    charges = Decimal("1000.00")
    revenues = Decimal("0.00")
    expected_type = Account.ExpectedType.CHARGE
    visible_in_report = True

    class Meta:
        model = Account


class GroupResponsibilityFactory(DjangoModelFactory):
    group = factory.SubFactory(AccountGroupFactory)
    year = 2024
    responsible = factory.SubFactory(UserFactory)

    class Meta:
        model = GroupResponsibility


class AvailableYearFactory(DjangoModelFactory):
    year = 2024
    type = AvailableYear.YearType.BUDGET

    class Meta:
        model = AvailableYear


class AccountCodeMappingFactory(DjangoModelFactory):
    mch1_function = factory.Sequence(lambda n: str(500 + n))
    mch1_nature = "301"
    mch1_sub_account = ""
    mch2_function = factory.Sequence(lambda n: str(10000 + n))
    mch2_nature = "3010"
    mch2_sub_account = ""

    class Meta:
        model = AccountCodeMapping


class AccountBalanceTransferFactory(DjangoModelFactory):
    mch1_code = factory.Sequence(lambda n: f"{700 + n}.300")
    target_code = ""

    class Meta:
        model = AccountBalanceTransfer
        django_get_or_create = ("mch1_code",)


class AccountCommentFactory(DjangoModelFactory):
    account = factory.SubFactory(AccountFactory)
    author = factory.SubFactory(UserFactory)
    content = factory.Faker("text")

    class Meta:
        model = AccountComment
