from pathlib import Path
from re import fullmatch

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
MANUAL_SOURCE = "MCH1"
MANUAL_TARGET = ("Fctio MCH2", "Nat MCH2", "Ext MCH2")
NO_SOURCE = "0"
MAPPING_FIELDS = (
    "mch1_function",
    "mch1_nature",
    "mch1_sub_account",
    "mch2_function",
    "mch2_nature",
    "mch2_sub_account",
)

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
        parser.add_argument("--sheet", default=SHEET_NAME)
        parser.add_argument("--replace", action="store_true", help="Remove relations absent from this complete file.")

    def handle(self, *args, **options):
        excel_path: Path = options["excel_path"]
        dry_run: bool = options["dry_run"]

        if not excel_path.exists():
            message = f"File not found: {excel_path}"
            raise CommandError(message)

        rows = self._read_mapping_rows(excel_path, sheet=options["sheet"])
        self._apply(rows, dry_run=dry_run, replace=options["replace"])

    def _read_mapping_rows(self, excel_path: Path, *, sheet=SHEET_NAME) -> list[MappingRow]:
        """
        Returns one (mch1_function, mch1_nature, mch1_sub_account, mch2_function,
        mch2_nature, mch2_sub_account) tuple per row where *both* sides of the
        crosswalk are filled in. Rows with only an MCH2 side are brand-new MCH2
        accounts with no MCH1 history (nothing to map); fully blank rows are
        sheet padding. Neither needs a row here.
        """
        df = read_excel_sheet(excel_path, sheet, header=0)
        if MANUAL_SOURCE in df.columns:
            return self._read_manual_rows(df.fillna(""))
        required = {
            COL_MCH1_FUNCTION,
            COL_MCH1_NATURE,
            COL_MCH1_SUB_ACCOUNT,
            COL_MCH2_FUNCTION,
            COL_MCH2_NATURE,
            COL_MCH2_SUB_ACCOUNT,
        }
        if not required.issubset(df.columns):
            message = "Unrecognized mapping columns. No relations changed."
            raise CommandError(message)

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

    def _read_manual_rows(self, dataframe) -> list[MappingRow]:
        if not set(MANUAL_TARGET).issubset(dataframe.columns):
            message = "Missing MCH2 mapping columns. No relations changed."
            raise CommandError(message)
        rows = set()
        for index, row in dataframe.iterrows():
            source = str(row[MANUAL_SOURCE]).strip()
            if not source or source == NO_SOURCE:
                continue
            if not fullmatch(r"[0-9]+\.[0-9]+(?:\.[0-9]+)?", source):
                message = f"Invalid MCH1 account on row {index + 2}: {source}"
                raise CommandError(message)
            source_function, source_nature, *source_extensions = source.split(".")
            source_extension = source_extensions[0] if source_extensions else ""
            source_extension = "" if source_extension and int(source_extension) == 0 else source_extension
            target = tuple(
                self._normalize_mch2_part(row[column], width)
                for column, width in zip(
                    MANUAL_TARGET, (MCH2_FUNCTION_WIDTH, MCH2_NATURE_WIDTH, MCH2_SUB_ACCOUNT_WIDTH), strict=True
                )
            )
            if not all(part.isdigit() for part in target) or not target[0].strip("0") or not target[1].strip("0"):
                message = f"Invalid MCH2 account on row {index + 2}. No relations changed."
                raise CommandError(message)
            rows.add((source_function, source_nature, source_extension, *target))
        return sorted(rows)

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
            return "00" if width == MCH2_SUB_ACCOUNT_WIDTH else ""
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        text = str(value).strip().zfill(width)
        if width == MCH2_SUB_ACCOUNT_WIDTH:
            return text
        return "" if text == "0" * width else text

    def _apply(self, rows: list[MappingRow], *, dry_run: bool, replace: bool = False) -> None:
        if replace and not rows:
            message = "Refusing to replace the mapping with an empty file."
            raise CommandError(message)
        created = unchanged = removed = 0

        with transaction.atomic():
            if replace:
                incoming = set(rows)
                obsolete = [
                    record[0]
                    for record in AccountCodeMapping.objects.select_for_update().values_list("pk", *MAPPING_FIELDS)
                    if record[1:] not in incoming
                ]
                removed, _ = AccountCodeMapping.objects.filter(pk__in=obsolete).delete()
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
        self.stdout.write(self.style.SUCCESS(f"{prefix}{created} created, {unchanged} unchanged, {removed} removed"))
