from pathlib import Path

import pandas as pd
from django.conf import settings
from django.core.management.base import BaseCommand
from django.core.management.base import CommandError
from django.db import transaction

from budgetis.accounting.models import AccountCodeMapping

from ._excel import read_excel_sheet


SHEET_NAME = "Fonctionnement"
COL_MCH1_FUNCTION, COL_MCH1_NATURE, COL_MCH1_SUB_ACCOUNT = "ADMIN1", "F", "NAT2"
COL_MCH2_FUNCTION, COL_MCH2_NATURE, COL_MCH2_SUB_ACCOUNT = "ADMIN1_N", "NAT1_N", "NAT2_N"

# MCH2 function = 4-digit canonical group code (N4) + 1 commune-specific digit;
# MCH2 nature = 4 digits; MCH2 subaccount = 2 digits. Pandas reads these numeric-
# looking columns as int, which silently drops any leading zero, so the original
# width has to be restored on import (see budgetis.accounting.models.AccountGroup
# for the same MCH2_GROUP_CODE_LENGTH convention on the function code).
MCH2_FUNCTION_WIDTH = 5
MCH2_NATURE_WIDTH = 4
MCH2_SUB_ACCOUNT_WIDTH = 2

DEFAULT_EXCEL_PATH = settings.BASE_DIR / "docs" / "external documents" / "Genolier - Modèle Fichier de conversion.xlsx"

MappingRow = tuple[str, str, str, str, str, str]


class Command(BaseCommand):
    help = (
        "Import Genolier's own MCH1->MCH2 account code crosswalk (tab 'Fonctionnement') into "
        "AccountCodeMapping, used to resolve per-account history across the scheme transition "
        "(see budgetis.accounting.scheme_transition)."
    )

    def add_arguments(self, parser):
        parser.add_argument("excel_path", type=Path, nargs="?", default=DEFAULT_EXCEL_PATH)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        excel_path: Path = options["excel_path"]
        dry_run: bool = options["dry_run"]

        if not excel_path.exists():
            message = f"File not found: {excel_path}"
            raise CommandError(message)

        rows = self._read_mapping_rows(excel_path)
        self._apply(rows, dry_run=dry_run)

    def _read_mapping_rows(self, excel_path: Path) -> list[MappingRow]:
        """
        Returns one (mch1_function, mch1_nature, mch1_sub_account, mch2_function,
        mch2_nature, mch2_sub_account) tuple per row where *both* sides of the
        crosswalk are filled in. Rows with only an MCH2 side are brand-new MCH2
        accounts with no MCH1 history (nothing to map); fully blank rows are
        sheet padding. Neither needs a row here.
        """
        df = read_excel_sheet(excel_path, SHEET_NAME, header=0)

        rows: list[MappingRow] = []
        for _, row in df.iterrows():
            if pd.isna(row[COL_MCH1_FUNCTION]) or pd.isna(row[COL_MCH2_FUNCTION]):
                continue

            rows.append(
                (
                    self._normalize_mch1_part(row[COL_MCH1_FUNCTION]),
                    self._normalize_mch1_part(row[COL_MCH1_NATURE]),
                    self._normalize_mch1_part(row[COL_MCH1_SUB_ACCOUNT]),
                    self._normalize_mch2_part(row[COL_MCH2_FUNCTION], MCH2_FUNCTION_WIDTH),
                    self._normalize_mch2_part(row[COL_MCH2_NATURE], MCH2_NATURE_WIDTH),
                    self._normalize_mch2_part(row[COL_MCH2_SUB_ACCOUNT], MCH2_SUB_ACCOUNT_WIDTH),
                )
            )

        return rows

    @staticmethod
    def _normalize_mch1_part(value) -> str:
        if pd.isna(value):
            return ""
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        text = str(value).strip()
        return "" if text == "0" else text

    @staticmethod
    def _normalize_mch2_part(value, width: int) -> str:
        if pd.isna(value):
            return ""
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        text = str(value).strip().zfill(width)
        return "" if text == "0" * width else text

    def _apply(self, rows: list[MappingRow], *, dry_run: bool) -> None:
        # No mutable field beyond the crosswalk's own identity, so a row either
        # already exists (unchanged) or gets created — nothing to update.
        created = unchanged = 0

        with transaction.atomic():
            for mch1_function, mch1_nature, mch1_sub_account, mch2_function, mch2_nature, mch2_sub_account in rows:
                _, was_created = AccountCodeMapping.objects.get_or_create(
                    mch1_function=mch1_function,
                    mch1_nature=mch1_nature,
                    mch1_sub_account=mch1_sub_account,
                    mch2_function=mch2_function,
                    mch2_nature=mch2_nature,
                    mch2_sub_account=mch2_sub_account,
                )
                created += was_created
                unchanged += not was_created

            if dry_run:
                transaction.set_rollback(True)

        prefix = "[DRY RUN] " if dry_run else ""
        self.stdout.write(self.style.SUCCESS(f"{prefix}{created} created, {unchanged} unchanged"))
