from collections import OrderedDict
from decimal import Decimal

from ..models import Account
from ..models import GroupResponsibility


class AccountExplorerMixin:
    def get_accounts(self, user, year: int, *, only_responsible: bool) -> list[Account]:
        """
        Return queryset of accounts for given year, filtered by responsibility if needed.
        """
        qs = Account.objects.filter(
            year=year,
            is_budget=False,
            group__isnull=False,
        ).select_related("group__supergroup__metagroup")

        if only_responsible:
            group_ids = GroupResponsibility.objects.filter(year=year, responsible=user).values_list(
                "group_id", flat=True
            )
            qs = qs.filter(group__in=group_ids)

        actual_accounts = list(qs)

        # Prepare keys for matching with budget accounts
        account_keys = {(a.function, a.nature, a.sub_account): a for a in actual_accounts}

        # Get corresponding budget accounts
        budget_accounts = Account.objects.filter(
            year=year,
            is_budget=True,
            function__in=[k[0] for k in account_keys],
            nature__in=[k[1] for k in account_keys],
        )

        # Map budget accounts back to actual accounts
        for b in budget_accounts:
            key = (b.function, b.nature, b.sub_account)
            actual = account_keys.get(key)
            if actual:
                actual.budget_charges = b.charges
                actual.budget_revenues = b.revenues

        # Default values if no match
        for a in actual_accounts:
            if not hasattr(a, "budget_charges"):
                a.budget_charges = Decimal("0.00")
            if not hasattr(a, "budget_revenues"):
                a.budget_revenues = Decimal("0.00")

        return actual_accounts

    def build_grouped_structure(self, accounts: list[Account]) -> OrderedDict:
        """
        Build nested structure: MetaGroup > SuperGroup > AccountGroup > Accounts
        with totals and labels.
        """
        if not accounts:
            return OrderedDict()

        year = accounts[0].year

        responsibilities = {
            r.group_id: r.responsible
            for r in GroupResponsibility.objects.filter(year=year).select_related("responsible")
        }

        raw_structure: dict[int, dict] = {}

        for account in accounts:
            group = account.group
            supergroup = group.supergroup if group else None
            metagroup = supergroup.metagroup if supergroup else None

            if not (group and supergroup and metagroup):
                continue

            mg_key = metagroup.code
            sg_key = supergroup.code
            ag_key = group.code

            mg = raw_structure.setdefault(
                mg_key,
                {
                    "label": metagroup.label,
                    "supergroups": {},
                },
            )

            sg = mg["supergroups"].setdefault(
                sg_key,
                {
                    "label": supergroup.label,
                    "groups": {},
                },
            )

            # ajout dans ag = sg["groups"].setdefault(...)
            ag = sg["groups"].setdefault(
                ag_key,
                {
                    "label": group.label,
                    "accounts": [],
                    "total_charges": Decimal(0),
                    "total_revenues": Decimal(0),
                    "budget_total_charges": Decimal(0),
                    "budget_total_revenues": Decimal(0),
                    "responsible": responsibilities.get(group.id),
                },
            )

            ag["accounts"].append(account)
            ag["total_charges"] += account.charges
            ag["total_revenues"] += account.revenues
            ag["budget_total_charges"] += account.budget_charges
            ag["budget_total_revenues"] += account.budget_revenues

        return self.sort_grouped_structure(raw_structure)

    def sort_grouped_structure(self, raw_structure: dict) -> OrderedDict:
        """
        Sort the nested structure by code at each level, and sort accounts by full code.
        """
        sorted_structure = OrderedDict()

        for mg_code in sorted(raw_structure.keys()):
            mg_data = raw_structure[mg_code]
            sorted_sg = OrderedDict()

            for sg_code in sorted(mg_data["supergroups"].keys()):
                sg_data = mg_data["supergroups"][sg_code]
                sorted_ag = OrderedDict()

                for ag_code in sorted(sg_data["groups"].keys()):
                    ag_data = sg_data["groups"][ag_code]
                    ag_data["accounts"] = sorted(
                        ag_data["accounts"], key=lambda a: (a.function, a.nature, a.sub_account or "")
                    )
                    sorted_ag[ag_code] = ag_data

                sg_data["groups"] = sorted_ag
                sorted_sg[sg_code] = sg_data

            mg_data["supergroups"] = sorted_sg
            sorted_structure[mg_code] = mg_data

        return sorted_structure
