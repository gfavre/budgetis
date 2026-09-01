from decimal import Decimal
from pathlib import Path

import pandas as pd
from django.conf import settings
from django.core.management.base import BaseCommand
from django.core.management.base import CommandError
from django.db import transaction

from budgetis.accounting.models import Account
from budgetis.common.models import ChartScheme
from budgetis.finance.models import AvailableYear

from ._excel import read_excel_sheet


SHEET_NAME = "Fonctionnement"
COL_FUNCTION, COL_NATURE, COL_SUB_ACCOUNT, COL_LABEL = "ADMIN1_N", "NAT1_N", "NAT2_N", "LIBELLÉ_N"

# Same widths as import_account_code_mapping: pandas reads these numeric-looking
# columns as int, silently dropping the leading zero that makes up the commune-
# specific digit (e.g. "01100"), so the original width has to be restored.
FUNCTION_WIDTH = 5
NATURE_WIDTH = 4
SUB_ACCOUNT_WIDTH = 2

# MCH2 nature ranges (see CLAUDE.md): 3xxx = charges, 4xxx = revenues.
CHARGE_NATURE_PREFIX = "3"
REVENUE_NATURE_PREFIX = "4"

DEFAULT_EXCEL_PATH = settings.BASE_DIR / "docs" / "external documents" / "Genolier - Modèle Fichier de conversion.xlsx"

AccountRow = tuple[str, str, str, str]


class Command(BaseCommand):
    help = (
        "Bootstrap a zero-value MCH2 account skeleton for the given year, one Account per "
        "distinct MCH2 line in Genolier's own conversion file (tab 'Fonctionnement') - so the "
        "explorer, responsibilities and comments have something to attach to before a real BDI "
        "import brings in actual figures. Never overwrites an existing account: once a row has "
        "real data (from BDI import or a human edit), reruns leave it untouched."
    )

    def add_arguments(self, parser):
        parser.add_argument("excel_path", type=Path, nargs="?", default=DEFAULT_EXCEL_PATH)
        parser.add_argument("--year", type=int, required=True)
        parser.add_argument("--actuals", action="store_true", help="Create actuals rows instead of budget rows.")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        year: int = options["year"]
        excel_path: Path = options["excel_path"]
        is_budget = not options["actuals"]
        dry_run: bool = options["dry_run"]

        if not excel_path.exists():
            message = f"File not found: {excel_path}"
            raise CommandError(message)

        rows = self._read_account_rows(excel_path)
        self._apply(rows, year=year, is_budget=is_budget, dry_run=dry_run)

    def _read_account_rows(self, excel_path: Path) -> list[AccountRow]:
        """
        One (function, nature, sub_account, label) tuple per distinct MCH2 line.
        A merge (several MCH1 rows sharing one MCH2 target) repeats the same MCH2
        triple several times in the sheet - only the first occurrence is kept.
        """
        df = read_excel_sheet(excel_path, SHEET_NAME, header=0)

        rows: list[AccountRow] = []
        seen: set[tuple[str, str, str]] = set()
        for _, row in df.iterrows():
            if pd.isna(row[COL_FUNCTION]):
                continue

            function = self._normalize(row[COL_FUNCTION], FUNCTION_WIDTH)
            nature = self._normalize(row[COL_NATURE], NATURE_WIDTH)
            sub_account = self._normalize(row[COL_SUB_ACCOUNT], SUB_ACCOUNT_WIDTH)
            key = (function, nature, sub_account)
            if key in seen:
                continue
            seen.add(key)

            label = "" if pd.isna(row[COL_LABEL]) else str(row[COL_LABEL]).strip()
            rows.append((function, nature, sub_account, label))

        return rows

    @staticmethod
    def _normalize(value, width: int) -> str:
        if pd.isna(value):
            return ""
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        text = str(value).strip().zfill(width)
        return "" if text == "0" * width else text

    @staticmethod
    def _expected_type(nature: str) -> str:
        if nature.startswith(CHARGE_NATURE_PREFIX):
            return Account.ExpectedType.CHARGE
        if nature.startswith(REVENUE_NATURE_PREFIX):
            return Account.ExpectedType.REVENUE
        return Account.ExpectedType.BOTH

    def _apply(self, rows: list[AccountRow], *, year: int, is_budget: bool, dry_run: bool) -> None:
        created = skipped = 0

        with transaction.atomic():
            AvailableYear.objects.get_or_create(
                year=year,
                type=AvailableYear.YearType.BUDGET if is_budget else AvailableYear.YearType.ACTUAL,
                defaults={"scheme": ChartScheme.MCH2},
            )

            for function, nature, sub_account, label in rows:
                _, was_created = Account.objects.get_or_create(
                    year=year,
                    function=function,
                    nature=nature,
                    sub_account=sub_account,
                    is_budget=is_budget,
                    defaults={
                        "label": label,
                        "scheme": ChartScheme.MCH2,
                        "charges": Decimal("0.00"),
                        "revenues": Decimal("0.00"),
                        "expected_type": self._expected_type(nature),
                    },
                )
                created += was_created
                skipped += not was_created

            if dry_run:
                transaction.set_rollback(True)

        prefix = "[DRY RUN] " if dry_run else ""
        self.stdout.write(self.style.SUCCESS(f"{prefix}{created} created, {skipped} already existed"))
