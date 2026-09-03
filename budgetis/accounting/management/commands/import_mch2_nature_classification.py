from pathlib import Path

import pandas as pd
from django.conf import settings
from django.core.management.base import BaseCommand
from django.core.management.base import CommandError
from django.db import transaction

from budgetis.accounting.models import NatureGroup
from budgetis.common.models import ChartScheme

from ._excel import read_excel_sheet


SHEET_NAMES = ("Compte de résultats - Charges", "Compte de résultats - Revenus")
HEADER_ROWS = 2
COL_GROUP, COL_ACCOUNT, COL_LABEL = 0, 1, 2
DEFAULT_EXCEL_PATH = settings.BASE_DIR / "docs" / "external documents" / "Plan_comptable_MCH2__Excel___04.26.xlsx"

ClassificationRow = tuple[int, str, str, str | None]  # level, code, label, parent_code


class Command(BaseCommand):
    help = (
        "One-shot import of the official MCH2 nature classification (charges and revenues, "
        "levels 1-4) from the canton's reference Excel file, into NatureGroup(scheme=MCH2)."
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

        rows: list[ClassificationRow] = []
        for sheet_name in SHEET_NAMES:
            rows += self._read_classification_rows(excel_path, sheet_name)
        self._apply(rows, dry_run=dry_run)

    def _read_classification_rows(self, excel_path: Path, sheet_name: str) -> list[ClassificationRow]:
        """
        Returns one (level, code, label, parent_code) tuple per node in this sheet,
        in the sheet's own depth-first order (a node's parent always appears
        earlier). Unlike the functional classification, levels 1-3 share a single
        "Groupe" column (the level is the digit count) and level 4 lives in its
        own "Compte" column.
        """
        df = read_excel_sheet(excel_path, sheet_name, header=None, skiprows=HEADER_ROWS)

        rows: list[ClassificationRow] = []
        last_code_by_level: dict[int, str] = {}

        for _, row in df.iterrows():
            label = row[COL_LABEL]
            if pd.isna(label):
                continue

            group_value, account_value = row[COL_GROUP], row[COL_ACCOUNT]
            if pd.notna(group_value):
                code = self._normalize_code(group_value)
                level = len(code)
            elif pd.notna(account_value):
                code = self._normalize_code(account_value)
                level = 4
            else:
                continue

            if not code.isdigit():
                # The sheet uses a literal "----" row as a visual section
                # divider between subcategories - not a real account code.
                continue

            parent_code = last_code_by_level.get(level - 1) if level > 1 else None
            rows.append((level, code, str(label).strip(), parent_code))
            last_code_by_level[level] = code

        return rows

    @staticmethod
    def _normalize_code(value) -> str:
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        return str(value).strip()

    def _apply(self, rows: list[ClassificationRow], *, dry_run: bool) -> None:
        created = updated = unchanged = 0
        groups_by_level_code: dict[tuple[int, str], NatureGroup] = {}

        with transaction.atomic():
            for level, code, label, parent_code in rows:
                parent = groups_by_level_code.get((level - 1, parent_code)) if parent_code else None
                existing = NatureGroup.objects.filter(scheme=ChartScheme.MCH2, level=level, code=code).first()

                if existing and existing.label == label and existing.parent_id == (parent.id if parent else None):
                    groups_by_level_code[(level, code)] = existing
                    unchanged += 1
                    continue

                group, was_created = NatureGroup.objects.update_or_create(
                    scheme=ChartScheme.MCH2,
                    level=level,
                    code=code,
                    defaults={"label": label, "parent": parent},
                )
                groups_by_level_code[(level, code)] = group
                created += was_created
                updated += not was_created

            if dry_run:
                transaction.set_rollback(True)

        prefix = "[DRY RUN] " if dry_run else ""
        self.stdout.write(self.style.SUCCESS(f"{prefix}{created} created, {updated} updated, {unchanged} unchanged"))
