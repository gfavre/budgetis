from io import StringIO
from unittest.mock import patch

import pandas as pd
import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from budgetis.accounting.models import AccountCodeMapping
from budgetis.accounting.tests.factories import AccountCodeMappingFactory
from budgetis.accounting.tests.factories import AccountCommentFactory
from budgetis.accounting.tests.factories import AccountFactory


pytestmark = pytest.mark.django_db
MANUAL_COLUMNS = ["MCH1", "Fctio MCH2", "Nat MCH2", "Ext MCH2", "Libellé MCH2"]


def sync(tmp_path, rows, **options):
    path = tmp_path / "mapping.xlsx"
    path.touch()
    with patch(
        "budgetis.accounting.management.commands.import_account_code_mapping.read_excel_sheet",
        return_value=pd.DataFrame(rows, columns=MANUAL_COLUMNS),
    ):
        call_command("import_account_code_mapping", str(path), stdout=StringIO(), **options)


def test_replace_removes_obsolete_extension_preserves_common_ids_and_account_data(tmp_path):
    obsolete = AccountCodeMappingFactory(
        mch1_function="580", mch1_nature="352", mch2_function="35001", mch2_nature="3612", mch2_sub_account="00"
    )
    common = AccountCodeMappingFactory(
        mch1_function="100", mch1_nature="300", mch2_function="01100", mch2_nature="3000", mch2_sub_account="00"
    )
    account = AccountFactory(charges=123)
    comment = AccountCommentFactory(account=account)
    rows = [
        ["580.352", "35001", "3612", "18", "Paroisses"],
        ["100.300", "01100", "3000", "00", "Commissions"],
        ["580.352", "35001", "3612", "18", "Duplicate"],
        ["0", "01100", "3000", "01", "New account"],
    ]
    sync(tmp_path, rows, replace=True)
    sync(tmp_path, rows, replace=True)
    assert not AccountCodeMapping.objects.filter(pk=obsolete.pk).exists()
    assert AccountCodeMapping.objects.filter(pk=common.pk).exists()
    assert AccountCodeMapping.objects.count() == len(rows) // 2
    assert AccountCodeMapping.objects.get(mch1_function="580").mch2_sub_account == "18"
    account.refresh_from_db()
    comment.refresh_from_db()
    assert account.charges == 123  # noqa: PLR2004
    assert comment.account_id == account.pk


def test_dry_run_rolls_back_removals_and_additions(tmp_path):
    existing = AccountCodeMappingFactory()
    sync(tmp_path, [["580.352", "35001", "3612", "18", "Paroisses"]], replace=True, dry_run=True)
    assert list(AccountCodeMapping.objects.values_list("pk", flat=True)) == [existing.pk]


@pytest.mark.parametrize("rows", [[], [["0", "01100", "3000", "00", "New"]]])
def test_replace_refuses_empty_mapping(tmp_path, rows):
    existing = AccountCodeMappingFactory()
    with pytest.raises(CommandError, match="empty file"):
        sync(tmp_path, rows, replace=True)
    assert AccountCodeMapping.objects.filter(pk=existing.pk).exists()


@pytest.mark.parametrize(
    "row", [["invalid", "35001", "3612", "18", "Bad source"], ["580.352", "", "3612", "18", "Bad target"]]
)
def test_invalid_row_prevents_any_changes(tmp_path, row):
    existing = AccountCodeMappingFactory()
    with pytest.raises(CommandError, match="Invalid"):
        sync(tmp_path, [["100.300", "01100", "3000", "00", "Valid"], row], replace=True)
    assert list(AccountCodeMapping.objects.values_list("pk", flat=True)) == [existing.pk]


def test_append_remains_available_and_normalizes_mch1_zero_extension(tmp_path):
    existing = AccountCodeMappingFactory()
    sync(tmp_path, [["580.352.00", "35001", "3612", "0", "Paroisses"]])
    assert AccountCodeMapping.objects.filter(pk=existing.pk).exists()
    relation = AccountCodeMapping.objects.get(mch1_function="580")
    assert relation.mch1_sub_account == ""
    assert relation.mch2_sub_account == "00"
