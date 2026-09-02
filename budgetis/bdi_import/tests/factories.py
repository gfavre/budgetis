import factory
from factory.django import DjangoModelFactory

from budgetis.bdi_import.models import AccountImportLog
from budgetis.bdi_import.models import ColumnMapping


class AccountImportLogFactory(DjangoModelFactory):
    year = 2024
    is_budget = True
    kind = AccountImportLog.ImportKind.BDI

    class Meta:
        model = AccountImportLog


class ColumnMappingFactory(DjangoModelFactory):
    log = factory.SubFactory(AccountImportLogFactory)
    field = ColumnMapping.Field.CODE
    column_name = "Code"

    class Meta:
        model = ColumnMapping
