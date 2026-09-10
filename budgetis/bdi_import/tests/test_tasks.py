from decimal import Decimal
from unittest.mock import patch

import pandas as pd
import pytest

from budgetis.accounting.models import Account
from budgetis.bdi_import.models import AccountImportLog
from budgetis.bdi_import.models import ColumnMapping
from budgetis.bdi_import.tasks import import_accounts_task
from budgetis.bdi_import.tests.factories import AccountImportLogFactory
from budgetis.bdi_import.tests.factories import ColumnMappingFactory


pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    ("kind", "credit", "expected"),
    [
        (AccountImportLog.ImportKind.EXCEL, "15880593.90", "15880593.90"),
        (AccountImportLog.ImportKind.BDI, "-15880593.90", "15880593.90"),
        (AccountImportLog.ImportKind.EXCEL, "-100", "-100"),
        (AccountImportLog.ImportKind.BDI, "100", "-100"),
    ],
)
def test_import_task_preserves_revenue_convention(kind, credit, expected):
    log = AccountImportLogFactory(kind=kind, file="imports/budget.xlsx")
    for field in (ColumnMapping.Field.CODE, ColumnMapping.Field.LABEL, ColumnMapping.Field.REVENUES):
        ColumnMappingFactory(log=log, field=field, column_name=field)
    rows = pd.DataFrame([{"code": "100.400", "label": "Revenue", "revenues": credit}])

    with patch("budgetis.bdi_import.tasks.load_account_dataframe", return_value=rows):
        import_accounts_task.run(log.pk)

    log.refresh_from_db()
    assert log.status == AccountImportLog.Status.SUCCESS
    assert Account.objects.get(year=log.year).revenues == Decimal(expected)


@pytest.mark.parametrize("kind", AccountImportLog.ImportKind)
def test_signed_total_uses_same_convention_for_both_import_kinds(kind):
    log = AccountImportLogFactory(kind=kind, file="imports/budget.xlsx")
    for field in (ColumnMapping.Field.CODE, ColumnMapping.Field.LABEL, ColumnMapping.Field.TOTAL):
        ColumnMappingFactory(log=log, field=field, column_name=field)
    rows = pd.DataFrame([{"code": "100.400", "label": "Revenue", "total": "-100"}])

    with patch("budgetis.bdi_import.tasks.load_account_dataframe", return_value=rows):
        import_accounts_task.run(log.pk)

    assert Account.objects.get(year=log.year).revenues == Decimal("100")
