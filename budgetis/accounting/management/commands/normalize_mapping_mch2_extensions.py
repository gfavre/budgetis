from django.core.management.base import BaseCommand
from django.db import transaction

from budgetis.accounting.models import AccountCodeMapping


class Command(BaseCommand):
    help = "Normalise les extensions MCH2 vides ou 0 du mapping en 00, sans modifier MCH1."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Simuler sans enregistrer les changements.")

    def handle(self, *args, **options):
        normalized = duplicates = 0
        with transaction.atomic():
            mappings = (
                AccountCodeMapping.objects.select_for_update()
                .filter(mch2_sub_account__in=["", "0"])
                .exclude(mch2_function="")
                .exclude(mch2_nature="")
                .order_by("pk")
            )
            for mapping in mappings:
                existing = AccountCodeMapping.objects.select_for_update().filter(
                    mch1_function=mapping.mch1_function,
                    mch1_nature=mapping.mch1_nature,
                    mch1_sub_account=mapping.mch1_sub_account,
                    mch2_function=mapping.mch2_function,
                    mch2_nature=mapping.mch2_nature,
                    mch2_sub_account="00",
                )
                if existing.exists():
                    # Same relation on both sides; this is not a split or merge.
                    mapping.delete()
                    duplicates += 1
                else:
                    AccountCodeMapping.objects.filter(pk=mapping.pk).update(mch2_sub_account="00")
                    normalized += 1
            if options["dry_run"]:
                transaction.set_rollback(True)
        prefix = "[SIMULATION] " if options["dry_run"] else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}{normalized} extensions normalisées; {duplicates} relations identiques dédoublonnées."
            )
        )
