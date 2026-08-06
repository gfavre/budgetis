from pathlib import Path

import pandas as pd
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.core.management.base import CommandError
from django.db import transaction

from budgetis.accounting.models import AccountGroup
from budgetis.accounting.models import GroupResponsibility


COLUMN_CODE = "No"
COLUMN_TRIGRAM = "Resp BUD"


class Command(BaseCommand):
    help = "One-shot import of AccountGroup responsibles (trigram) from an Excel export, for a given year."

    def add_arguments(self, parser):
        parser.add_argument("excel_path", type=Path)
        parser.add_argument("--year", type=int, required=True)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        excel_path: Path = options["excel_path"]
        year: int = options["year"]
        dry_run: bool = options["dry_run"]

        if not excel_path.exists():
            message = f"File not found: {excel_path}"
            raise CommandError(message)

        function_trigrams = self._read_function_trigrams(excel_path)
        self._apply(function_trigrams, year, dry_run=dry_run)

    def _read_function_trigrams(self, excel_path: Path) -> dict[str, str]:
        df = pd.read_excel(excel_path, dtype=str).dropna(subset=[COLUMN_CODE])

        function_trigrams: dict[str, str] = {}
        conflicts: dict[str, set[str]] = {}
        for _, row in df.iterrows():
            code = str(row[COLUMN_CODE]).strip()
            raw_trigram = row.get(COLUMN_TRIGRAM)
            if not code or pd.isna(raw_trigram):
                continue
            trigram = str(raw_trigram).strip().upper()
            if not trigram:
                continue

            function = code.split(".")[0]
            if not function.isdigit():
                continue

            existing = function_trigrams.get(function)
            if existing and existing != trigram:
                conflicts.setdefault(function, {existing}).add(trigram)
                continue
            function_trigrams[function] = trigram

        for function, trigrams in conflicts.items():
            self.stderr.write(self.style.WARNING(f"Skipping {function}: conflicting trigrams {sorted(trigrams)}"))
            function_trigrams.pop(function, None)

        return function_trigrams

    def _apply(self, function_trigrams: dict[str, str], year: int, *, dry_run: bool) -> None:
        groups = {g.code: g for g in AccountGroup.objects.filter(code__in=function_trigrams)}
        users = {u.trigram: u for u in get_user_model().objects.filter(trigram__in=set(function_trigrams.values()))}
        existing = {
            r.group_id: r for r in GroupResponsibility.objects.filter(year=year, group__code__in=function_trigrams)
        }

        updated = unchanged = skipped = 0

        with transaction.atomic():
            for function, trigram in sorted(function_trigrams.items()):
                group = groups.get(function)
                user = users.get(trigram)

                if not group:
                    self.stderr.write(self.style.WARNING(f"No AccountGroup with code {function!r}"))
                    skipped += 1
                    continue
                if not user:
                    self.stderr.write(self.style.WARNING(f"No User with trigram {trigram!r} (group {function})"))
                    skipped += 1
                    continue

                current = existing.get(group.id)
                if current and current.responsible_id == user.id:
                    unchanged += 1
                    continue

                previous = current.responsible.trigram if current and current.responsible else "unset"
                self.stdout.write(f"{function} ({group.label}): {previous} -> {trigram}")
                updated += 1
                GroupResponsibility.objects.update_or_create(group=group, year=year, defaults={"responsible": user})

            if dry_run:
                transaction.set_rollback(True)

        prefix = "[DRY RUN] " if dry_run else ""
        self.stdout.write(self.style.SUCCESS(f"{prefix}{updated} updated, {unchanged} unchanged, {skipped} skipped"))
