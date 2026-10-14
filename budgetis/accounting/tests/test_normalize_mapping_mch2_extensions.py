from io import StringIO

import pytest
from django.core.management import call_command

from budgetis.accounting.models import AccountCodeMapping
from budgetis.accounting.scheme_transition import MappingKind
from budgetis.accounting.scheme_transition import classify_mch2_account


pytestmark = pytest.mark.django_db


def mapping(extension="", **kwargs):
    fields = {
        "mch1_function": "100",
        "mch1_nature": "300",
        "mch1_sub_account": "0",
        "mch2_function": "01100",
        "mch2_nature": "3000",
        "mch2_sub_account": extension,
    }
    return AccountCodeMapping.objects.create(**(fields | kwargs))


def run(**kwargs):
    call_command("normalize_mapping_mch2_extensions", stdout=StringIO(), **kwargs)


@pytest.mark.parametrize("extension", ["", "0"])
def test_normalizes_without_changing_mch1_and_is_idempotent(extension):
    row = mapping(extension)
    run()
    run()
    row.refresh_from_db()
    assert row.mch2_sub_account == "00"
    assert row.mch1_sub_account == "0"
    assert classify_mch2_account("01100", "3000", "00").kind == MappingKind.ONE_TO_ONE
    assert AccountCodeMapping.objects.count() == 1


def test_deduplicates_only_identical_relations_preserving_splits_and_merges():
    blank = mapping()
    zero = mapping("0")
    canonical = mapping("00")
    split = mapping("01")
    merged = mapping(mch1_function="200")
    run()
    assert not AccountCodeMapping.objects.filter(pk__in=[blank.pk, zero.pk]).exists()
    for row in [canonical, split, merged]:
        assert AccountCodeMapping.objects.filter(pk=row.pk).exists()
    merged.refresh_from_db()
    assert merged.mch2_sub_account == "00"
    assert classify_mch2_account("01100", "3000", "00").kind == MappingKind.SPLIT


def test_dry_run_preserves_original_rows():
    blank = mapping()
    mapping("00")
    zero = mapping("0", mch1_function="200")
    original = list(AccountCodeMapping.objects.order_by("pk").values())
    run(dry_run=True)
    assert list(AccountCodeMapping.objects.order_by("pk").values()) == original
    blank.refresh_from_db()
    zero.refresh_from_db()
    assert blank.mch2_sub_account == ""
    assert zero.mch2_sub_account == "0"


def test_preserves_nonzero_extensions_and_incomplete_targets():
    rows = [mapping("01"), mapping("99"), mapping(mch2_function=""), mapping(mch2_nature="")]
    original = list(AccountCodeMapping.objects.order_by("pk").values())
    run()
    assert list(AccountCodeMapping.objects.order_by("pk").values()) == original
    assert all(AccountCodeMapping.objects.filter(pk=row.pk).exists() for row in rows)
