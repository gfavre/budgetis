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

        return list(qs)

    def build_grouped_structure(self, accounts: list[Account]) -> OrderedDict:
        """
        Build nested structure: MetaGroup > SuperGroup > AccountGroup > Accounts
        with totals and labels.
        """
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

            ag = sg["groups"].setdefault(
                ag_key,
                {
                    "label": group.label,
                    "accounts": [],
                    "total_charges": Decimal(0),
                    "total_revenues": Decimal(0),
                },
            )

            ag["accounts"].append(account)
            ag["total_charges"] += account.charges
            ag["total_revenues"] += account.revenues

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
                        ag_data["accounts"], key=lambda a: (a.function, a.nature, a.sub_account or 0)
                    )
                    sorted_ag[ag_code] = ag_data

                sg_data["groups"] = sorted_ag
                sorted_sg[sg_code] = sg_data

            mg_data["supergroups"] = sorted_sg
            sorted_structure[mg_code] = mg_data

        return sorted_structure
