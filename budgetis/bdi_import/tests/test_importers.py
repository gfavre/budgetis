from decimal import Decimal

import pandas as pd
import pytest

from budgetis.accounting.models import Account
from budgetis.accounting.models import GroupResponsibility
from budgetis.accounting.tests.factories import AccountFactory
from budgetis.accounting.tests.factories import AccountGroupFactory
from budgetis.bdi_import.importers import _extract_account_code
from budgetis.bdi_import.importers import _normalize_sub_account
from budgetis.bdi_import.importers import assign_row_responsible
from budgetis.bdi_import.importers import import_accounts_from_dataframe
from budgetis.users.tests.factories import UserFactory


pytestmark = pytest.mark.django_db


class TestNormalizeSubAccount:
    def test_all_zero_becomes_empty(self):
        assert _normalize_sub_account("00") == ""
        assert _normalize_sub_account("0") == ""

    def test_real_value_is_preserved_including_leading_zero(self):
        assert _normalize_sub_account("01") == "01"

    def test_non_numeric_is_preserved(self):
        assert _normalize_sub_account("A trouver") == "A trouver"


class TestExtractAccountCode:
    def test_combined_code_column(self):
        row = pd.Series({"Compte": "170.301.2"})
        assert _extract_account_code(row, {"code": "Compte"}) == ("170", "301", "2")

    def test_invalid_combined_code_returns_none(self):
        row = pd.Series({"Compte": "not-a-code"})
        assert _extract_account_code(row, {"code": "Compte"}) is None

    def test_empty_combined_code_returns_none(self):
        row = pd.Series({"Compte": ""})
        assert _extract_account_code(row, {"code": "Compte"}) is None

    def test_split_columns_without_sub_account_mapping(self):
        row = pd.Series({"Fctio": "01100", "Nat": "3000"})
        column_map = {"function": "Fctio", "nature": "Nat"}
        assert _extract_account_code(row, column_map) == ("01100", "3000", "")

    def test_split_columns_with_sub_account_mapping(self):
        row = pd.Series({"Fctio": "01100", "Nat": "3000", "Ext": "01"})
        column_map = {"function": "Fctio", "nature": "Nat", "sub_account": "Ext"}
        assert _extract_account_code(row, column_map) == ("01100", "3000", "01")

    def test_split_columns_all_zero_extension_normalizes_to_empty(self):
        row = pd.Series({"Fctio": "01100", "Nat": "3000", "Ext": "00"})
        column_map = {"function": "Fctio", "nature": "Nat", "sub_account": "Ext"}
        assert _extract_account_code(row, column_map) == ("01100", "3000", "")

    def test_missing_function_returns_none(self):
        row = pd.Series({"Fctio": "", "Nat": "3000"})
        column_map = {"function": "Fctio", "nature": "Nat"}
        assert _extract_account_code(row, column_map) is None

    def test_no_recognized_mapping_returns_none(self):
        row = pd.Series({"Something": "irrelevant"})
        assert _extract_account_code(row, {}) is None


class TestAssignRowResponsible:
    def test_creates_group_responsibility_for_known_trigram(self):
        user = UserFactory(trigram="ADA")
        group = AccountGroupFactory()
        account = AccountFactory(group=group, year=2027)
        row = pd.Series({"Resp": "ada"})

        assign_row_responsible(account, row, {"responsible": "Resp"}, 2027)

        responsibility = GroupResponsibility.objects.get(group=group, year=2027)
        assert responsibility.responsible == user

    def test_unknown_trigram_is_skipped(self):
        group = AccountGroupFactory()
        account = AccountFactory(group=group, year=2027)
        row = pd.Series({"Resp": "ZZZ"})

        assign_row_responsible(account, row, {"responsible": "Resp"}, 2027)

        assert not GroupResponsibility.objects.filter(group=group, year=2027).exists()

    def test_no_op_when_responsible_column_not_mapped(self):
        group = AccountGroupFactory()
        account = AccountFactory(group=group, year=2027)
        row = pd.Series({"Resp": "ADA"})

        assign_row_responsible(account, row, {}, 2027)

        assert not GroupResponsibility.objects.filter(group=group, year=2027).exists()

    def test_no_op_when_account_has_no_group(self):
        account = AccountFactory(group=None, year=2027)
        row = pd.Series({"Resp": "ADA"})

        assign_row_responsible(account, row, {"responsible": "Resp"}, 2027)

        assert GroupResponsibility.objects.count() == 0


class TestImportAccountsFromDataframeSplitColumns:
    def test_imports_split_columns_with_responsible_and_signed_total(self):
        user = UserFactory(trigram="ADA")
        group = AccountGroupFactory(code="01100", level=4)
        AccountGroupFactory(code="79010", level=4)

        account_rows = pd.DataFrame(
            [
                {
                    "Resp BUD": "ADA",
                    "Fctio MCH2": "01100",
                    "Nat MCH2": "3000",
                    "Ext MCH2": "00",
                    "Libellé MCH2": "Commissions",
                    "Budget 2027": "9000",
                },
                {
                    "Resp BUD": "ADA",
                    "Fctio MCH2": "79010",
                    "Nat MCH2": "4210",
                    "Ext MCH2": "00",
                    "Libellé MCH2": "Emoluments",
                    "Budget 2027": "-2000",
                },
            ]
        )
        column_map = {
            "function": "Fctio MCH2",
            "nature": "Nat MCH2",
            "sub_account": "Ext MCH2",
            "label": "Libellé MCH2",
            "total": "Budget 2027",
            "responsible": "Resp BUD",
        }

        import_accounts_from_dataframe(
            account_rows,
            year=2027,
            is_budget=True,
            column_map=column_map,
            derived_from_total=True,
        )

        charge_account = Account.objects.get(function="01100", nature="3000", year=2027)
        assert charge_account.charges == Decimal("9000")
        assert charge_account.revenues == Decimal("0")
        assert charge_account.sub_account == ""

        revenue_account = Account.objects.get(function="79010", nature="4210", year=2027)
        assert revenue_account.charges == Decimal("0")
        assert revenue_account.revenues == Decimal("2000")

        assert GroupResponsibility.objects.filter(group=group, year=2027, responsible=user).exists()

    def test_rows_sharing_the_same_target_account_are_summed_not_overwritten(self):
        # Regression: a manually-prepared sheet can have several MCH1-origin
        # rows collapsing onto the same MCH2 target (a merge) - their amounts
        # must add up. This previously let the last matching row silently
        # overwrite the earlier ones' amounts.
        AccountGroupFactory(code="79010", level=4)
        account_rows = pd.DataFrame(
            [
                {
                    "Fctio MCH2": "79010",
                    "Nat MCH2": "4210",
                    "Ext MCH2": "00",
                    "Libellé MCH2": "Emoluments (part 1)",
                    "Budget 2027": "-2000",
                },
                {
                    "Fctio MCH2": "79010",
                    "Nat MCH2": "4210",
                    "Ext MCH2": "00",
                    "Libellé MCH2": "Emoluments (part 2, no amount yet)",
                    "Budget 2027": "",
                },
            ]
        )
        column_map = {
            "function": "Fctio MCH2",
            "nature": "Nat MCH2",
            "sub_account": "Ext MCH2",
            "label": "Libellé MCH2",
            "total": "Budget 2027",
        }

        import_accounts_from_dataframe(
            account_rows,
            year=2027,
            is_budget=True,
            column_map=column_map,
            derived_from_total=True,
        )

        account = Account.objects.get(function="79010", nature="4210", year=2027)
        assert account.charges == Decimal("0")
        assert account.revenues == Decimal("2000")
        assert account.label == "Emoluments (part 1)"
