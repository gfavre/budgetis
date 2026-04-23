from decimal import Decimal

import factory
from factory.django import DjangoModelFactory

from budgetis.accounting.models import Account
from budgetis.accounting.models import AccountComment
from budgetis.accounting.models import AccountGroup
from budgetis.accounting.models import MetaGroup
from budgetis.accounting.models import SuperGroup
from budgetis.users.tests.factories import UserFactory


class MetaGroupFactory(DjangoModelFactory):
    code = factory.Sequence(lambda n: n + 1)
    label = factory.Faker("word")

    class Meta:
        model = MetaGroup


class SuperGroupFactory(DjangoModelFactory):
    code = factory.Sequence(lambda n: n + 10)
    label = factory.Faker("word")
    metagroup = factory.SubFactory(MetaGroupFactory)

    class Meta:
        model = SuperGroup


class AccountGroupFactory(DjangoModelFactory):
    code = factory.Sequence(lambda n: str(500 + n))
    label = factory.Faker("word")
    supergroup = factory.SubFactory(SuperGroupFactory)

    class Meta:
        model = AccountGroup


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


class AccountCommentFactory(DjangoModelFactory):
    account = factory.SubFactory(AccountFactory)
    author = factory.SubFactory(UserFactory)
    content = factory.Faker("text")

    class Meta:
        model = AccountComment
