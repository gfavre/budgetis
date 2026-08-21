from pathlib import Path

import pandas as pd
from django.conf import settings
from django.core.management.base import BaseCommand
from django.core.management.base import CommandError
from django.db import transaction

from budgetis.accounting.models import AccountGroup
from budgetis.common.models import ChartScheme


SHEET_NAME = "Classification fonctionnelle"
HEADER_ROWS = 3
COL_N1, COL_N2, COL_N3, COL_N4, COL_LABEL = 0, 1, 2, 3, 4
LEVEL_COLUMNS = ((1, COL_N1), (2, COL_N2), (3, COL_N3), (4, COL_N4))
LEVEL_WIDTHS = {1: 1, 2: 2, 3: 3, 4: 4}
DEFAULT_EXCEL_PATH = settings.BASE_DIR / "docs" / "external documents" / "Plan_comptable_MCH2__Excel___04.26.xlsx"

# The canton's own reference workbook transposes the digits of this one N3 code
# ("352" instead of "532"): its N4 child (5320) and its N2 parent (53, "Vieillesse
# et survivants") both point to 532, and 531/533 bracket it as siblings. Corrected
# on import rather than reproducing the source typo.
KNOWN_SOURCE_CORRECTIONS = {
    (3, "352"): "532",
}

ClassificationRow = tuple[int, str, str, str | None]  # level, code, label, parent_code


class Command(BaseCommand):
    help = (
        "One-shot import of the official MCH2 functional classification (N1-N4) from the "
        "canton's reference Excel file, into AccountGroup(scheme=MCH2). Genolier-specific "
        "commune digits/extensions are not part of this reference and are added later, with "
        "the accounts themselves."
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

        rows = self._read_classification_rows(excel_path)
        self._apply(rows, dry_run=dry_run)

    def _read_classification_rows(self, excel_path: Path) -> list[ClassificationRow]:
        """
        Returns one (level, code, label, parent_code) tuple per N1-N4 node, in the
        sheet's own depth-first order (a node's parent always appears earlier).
        """
        df = pd.read_excel(excel_path, sheet_name=SHEET_NAME, header=None, skiprows=HEADER_ROWS)

        rows: list[ClassificationRow] = []
        last_code_by_level: dict[int, str] = {}

        for _, row in df.iterrows():
            label = row[COL_LABEL]
            if pd.isna(label):
                continue

            for level, col in LEVEL_COLUMNS:
                raw_code = row[col]
                if pd.isna(raw_code):
                    continue
                code = self._normalize_code(raw_code, LEVEL_WIDTHS[level])
                code = KNOWN_SOURCE_CORRECTIONS.get((level, code), code)
                parent_code = last_code_by_level.get(level - 1) if level > 1 else None
                rows.append((level, code, str(label).strip(), parent_code))
                last_code_by_level[level] = code
                break  # exactly one of N1..N4 is populated per row

        return rows

    @staticmethod
    def _normalize_code(value, width: int) -> str:
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        return str(value).strip().zfill(width)

    def _apply(self, rows: list[ClassificationRow], *, dry_run: bool) -> None:
        created = updated = unchanged = 0
        groups_by_level_code: dict[tuple[int, str], AccountGroup] = {}

        with transaction.atomic():
            for level, code, label, parent_code in rows:
                parent = groups_by_level_code.get((level - 1, parent_code)) if parent_code else None
                existing = AccountGroup.objects.filter(scheme=ChartScheme.MCH2, level=level, code=code).first()

                if existing and existing.label == label and existing.parent_id == (parent.id if parent else None):
                    groups_by_level_code[(level, code)] = existing
                    unchanged += 1
                    continue

                group, was_created = AccountGroup.objects.update_or_create(
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
