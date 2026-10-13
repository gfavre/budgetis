from django.core.management.base import BaseCommand
from django.core.management.base import CommandError
from django.db import transaction

from budgetis.accounting.models import Account
from budgetis.accounting.models import AccountComment
from budgetis.common.models import ChartScheme


class Command(BaseCommand):
    help = "Remplace les extensions MCH2 vides par 00 et résout les doublons en interactif."

    def add_arguments(self, parser):
        parser.add_argument("--year", type=int, help="Limiter le nettoyage à une année.")
        parser.add_argument("--dry-run", action="store_true", help="Simuler sans enregistrer les changements.")

    def handle(self, *args, **options):
        accounts = Account.objects.filter(scheme=ChartScheme.MCH2, sub_account="")
        if options["year"] is not None:
            accounts = accounts.filter(year=options["year"])
        normalized = deleted = 0
        try:
            with transaction.atomic():
                # Lock both variants; changes and interactive decisions belong to
                # one transaction so an interrupted run leaves no partial cleanup.
                for account in accounts.select_for_update().order_by("year", "function", "nature", "is_budget"):
                    duplicate = (
                        Account.objects.select_for_update()
                        .filter(
                            year=account.year,
                            function=account.function,
                            nature=account.nature,
                            is_budget=account.is_budget,
                            sub_account="00",
                        )
                        .first()
                    )
                    if duplicate is not None:
                        # The database uniqueness key does not include scheme.
                        if duplicate.scheme != ChartScheme.MCH2:
                            message = f"Collision avec un compte non MCH2 : {duplicate}. Nettoyage annulé."
                            raise CommandError(message)
                        keeper = self._choose(account, duplicate)
                        discarded = duplicate if keeper.pk == account.pk else account
                        AccountComment.objects.filter(account=discarded).update(account=keeper)
                        self.stdout.write(f"Suppression #{discarded.pk} ; conservation #{keeper.pk}.")
                        discarded.delete()
                        deleted += 1
                        if keeper.pk != account.pk:
                            continue
                    # QuerySet.update avoids unrelated group reassignment in save().
                    Account.objects.filter(pk=account.pk).update(sub_account="00")
                    self.stdout.write(f"#{account.pk} : {account} -> extension 00")
                    normalized += 1
                if options["dry_run"]:
                    transaction.set_rollback(True)
        except (EOFError, KeyboardInterrupt) as exc:
            message = "Saisie interrompue : aucun changement enregistré. Utilisez un terminal interactif Docker."
            raise CommandError(message) from exc
        prefix = "[SIMULATION — aucun changement enregistré] " if options["dry_run"] else ""
        self.stdout.write(
            self.style.SUCCESS(f"{prefix}{normalized} extensions modifiées, {deleted} doublons supprimés.")
        )

    def _choose(self, account, duplicate):
        has_amount = bool(account.charges or account.revenues)
        duplicate_has_amount = bool(duplicate.charges or duplicate.revenues)
        if has_amount != duplicate_has_amount:
            return account if has_amount else duplicate
        self.stdout.write("Doublon : choisissez le compte à conserver (les montants ne seront pas additionnés).")
        for index, candidate in enumerate((account, duplicate), start=1):
            self.stdout.write(
                f"{index}. #{candidate.pk} {candidate} — "
                f"charges={candidate.charges}, revenus={candidate.revenues}, "
                f"commentaires={candidate.comments.count()}"
            )
        while True:
            choice = input("Conserver [1/2] ou annuler tout le nettoyage [q] : ").strip().lower()
            if choice == "q":
                message = "Nettoyage annulé : aucun changement enregistré."
                raise CommandError(message)
            if choice in {"1", "2"}:
                return account if choice == "1" else duplicate
            self.stdout.write("Réponse attendue : 1, 2 ou q.")
