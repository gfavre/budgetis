from collections import OrderedDict
from decimal import Decimal

from django.db.models import Count
from django.utils import formats
from django.utils.translation import gettext_lazy as _

from budgetis.bdi_import.models import AccountImportLog

from ..models import Account
from ..models import GroupResponsibility


class BaseExplorerLogicMixin:
    """
    Shared ORM and helper logic between AccountExplorerMixin and BudgetExplorerMixin.
    """

    # ---------- ORM helpers -------------------------------------------------

    def _get_accounts_queryset(self, *, year: int, is_budget: bool, group_ids: list[int] | None = None):
        """Return filtered queryset of Account, with proper selects and annotations."""
        qs = (
            Account.objects.filter(year=year, is_budget=is_budget, group__isnull=False, visible_in_report=True)
            .select_related("group__supergroup__metagroup")
            .annotate(comment_count=Count("comments"))
        )
        if group_ids:
            qs = qs.filter(group__in=group_ids)
        return qs

    def _get_group_ids(self, user, year: int, only_responsible: bool) -> list[int]:  # noqa: FBT001
        """Return list of group IDs for which the user is responsible."""
        if not only_responsible:
            return []
        return list(GroupResponsibility.objects.filter(year=year, responsible=user).values_list("group_id", flat=True))

    # ---------- Generic data attachers --------------------------------------

    @staticmethod
    def _ensure_budget_defaults(accounts: list[Account]) -> None:
        """Ensure every account has all budget attributes."""
        for a in accounts:
            if not hasattr(a, "budget_charges"):
                a.budget_charges = Decimal("0.00")
            if not hasattr(a, "budget_revenues"):
                a.budget_revenues = Decimal("0.00")
            if not hasattr(a, "budget_id"):
                a.budget_id = None
            if not hasattr(a, "budget_comment_count"):
                a.budget_comment_count = 0

    @staticmethod
    def _calc_pct(current: Decimal, previous: Decimal) -> Decimal | None:
        """Return percentage change, None if previous == 0."""
        if previous == 0:
            return None
        return ((current - previous) / previous * 100).quantize(Decimal("0.1"))


class AccountExplorerMixin(BaseExplorerLogicMixin):
    def get_accounts(self, user, year: int, *, only_responsible: bool) -> list[Account]:
        """
        Return queryset of accounts for a given year, filtered by responsibility if needed.
        Includes fallback to budget accounts if no actuals exist.
        """
        group_ids = self._get_group_ids(user, year, only_responsible)
        actual_accounts = self._get_actual_accounts(year, group_ids)

        if not actual_accounts:
            return self._get_budget_fallback(year, group_ids)

        self._attach_budget_data(year, actual_accounts)
        self._ensure_budget_defaults(actual_accounts)
        return actual_accounts

    def _get_budget_fallback(self, year: int, group_ids: list[int]) -> list[Account]:
        """If no actual accounts exist, return budget accounts with zeroed actual values."""
        qs = (
            Account.objects.filter(
                year=year,
                is_budget=True,
                group__isnull=False,
            )
            .select_related("group__supergroup__metagroup")
            .annotate(comment_count=Count("comments"))
        )
        if group_ids:
            qs = qs.filter(group__in=group_ids)

        accounts = list(qs)
        for b in accounts:
            b.budget_charges = b.charges
            b.budget_revenues = b.revenues
            b.budget_id = b.id
            b.budget_comment_count = b.comment_count  # type: ignore[attr-defined]
            b.charges = Decimal("0.00")
            b.revenues = Decimal("0.00")
        return accounts

    def _attach_budget_data(self, year: int, actual_accounts: list[Account]) -> None:
        """Attach corresponding budget data to actual accounts."""
        account_keys = {(a.function, a.nature, a.sub_account): a for a in actual_accounts}
        budget_qs = Account.objects.filter(
            year=year,
            is_budget=True,
            function__in=[k[0] for k in account_keys],
            nature__in=[k[1] for k in account_keys],
        ).annotate(comment_count=Count("comments"))

        for b in budget_qs:
            key = (b.function, b.nature, b.sub_account)
            actual = account_keys.get(key)
            if actual:
                actual.budget_charges = b.charges
                actual.budget_revenues = b.revenues
                actual.budget_id = b.id
                actual.budget_comment_count = b.comment_count  # type: ignore[attr-defined]

    def _ensure_budget_defaults(self, accounts: list[Account]) -> None:
        """Ensure each account has budget-related attributes even if unmatched."""
        for a in accounts:
            if not hasattr(a, "budget_charges"):
                a.budget_charges = Decimal("0.00")
            if not hasattr(a, "budget_revenues"):
                a.budget_revenues = Decimal("0.00")
            if not hasattr(a, "budget_id"):
                a.budget_id = None
            if not hasattr(a, "budget_comment_count"):
                a.budget_comment_count = 0

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
                {"label": metagroup.label, "supergroups": {}},
            )
            sg = mg["supergroups"].setdefault(
                sg_key,
                {
                    "label": supergroup.label,
                    "groups": {},
                    "total_charges": Decimal(0),
                    "total_revenues": Decimal(0),
                    "budget_total_charges": Decimal(0),
                    "budget_total_revenues": Decimal(0),
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

            # Totaux cumulés du supergroupe
            sg["total_charges"] += account.charges
            sg["total_revenues"] += account.revenues
            sg["budget_total_charges"] += account.budget_charges
            sg["budget_total_revenues"] += account.budget_revenues

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

    def get_last_import_info(self, year: int) -> str:
        """
        Return a human-readable string with the last import dates for budget and actual accounts.
        Example: "Dernier import : 12 janvier 2025 (budget)  •  8 août 2026 (comptes)"
        """

        def _get_date(is_budget: bool) -> str | None:  # noqa: FBT001
            log = (
                AccountImportLog.objects.filter(year=year, is_budget=is_budget, status="success")
                .order_by("-created_at")
                .first()
            )
            return formats.date_format(log.created_at, "j F Y") if log else None

        budget_date = _get_date(True)  # noqa: FBT003
        actual_date = _get_date(False)  # noqa: FBT003

        if not budget_date and not actual_date:
            return ""
        parts = []
        if budget_date:
            budget_lbl = _("budget")
            parts.append(f"{budget_date} ({budget_lbl})")
        if actual_date:
            actual_lbl = _("actuals")
            parts.append(f"{actual_date} ({actual_lbl})")
        return _("Last import:") + " " + "  •  ".join(parts)

    # ------------------------------------------------------------------
    # legacy accessors used by get_accounts (for partial views)
    # ------------------------------------------------------------------

    def _get_actual_accounts(self, year: int, group_ids: list[int]):
        """Return queryset for actual accounts of the given year."""
        qs = (
            Account.objects.filter(year=year, is_budget=False, group__isnull=False, visible_in_report=True)
            .select_related("group__supergroup__metagroup")
            .annotate(comment_count=Count("comments"))
        )
        # Only filter if the list of groups is non-empty
        if group_ids:
            qs = qs.filter(group_id__in=group_ids)
        return qs

    def _get_budget_accounts(self, year: int):
        """Return queryset for budget accounts of the given year."""
        return (
            Account.objects.filter(year=year, is_budget=True, group__isnull=False, visible_in_report=True)
            .select_related("group__supergroup__metagroup")
            .annotate(comment_count=Count("comments"))
        )


class BudgetExplorerMixin(AccountExplorerMixin):
    """Extend AccountExplorerMixin to handle year-1 and year-2 comparisons."""

    def get_accounts(self, user, year: int, *, only_responsible: bool) -> list[Account]:
        group_ids = self._get_group_ids(user, year, only_responsible)
        current_budget = list(self._get_accounts_queryset(year=year, is_budget=True, group_ids=group_ids))
        prev_budget = list(self._get_accounts_queryset(year=year - 1, is_budget=True))
        actuals = list(self._get_accounts_queryset(year=year - 2, is_budget=False))

        prev_map = {(a.function, a.nature, a.sub_account): a for a in prev_budget}
        act_map = {(a.function, a.nature, a.sub_account): a for a in actuals}

        for acc in current_budget:
            key = (acc.function, acc.nature, acc.sub_account)
            prev = prev_map.get(key)
            act = act_map.get(key)
            acc.prev_budget_charges = prev.charges if prev else Decimal("0.00")
            acc.prev_budget_revenues = prev.revenues if prev else Decimal("0.00")
            acc.actual_charges = act.charges if act else Decimal("0.00")
            acc.actual_revenues = act.revenues if act else Decimal("0.00")
            acc.charges_pct = self._calc_pct(acc.charges, acc.prev_budget_charges)
            acc.revenues_pct = self._calc_pct(acc.revenues, acc.prev_budget_revenues)
            acc.budget_charges = acc.charges
            acc.budget_revenues = acc.revenues
            acc.budget_id = acc.id
            acc.budget_comment_count = acc.comment_count or 0
        return current_budget

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
                    "budget_total_charges": Decimal(0),
                    "budget_total_revenues": Decimal(0),
                    "prev_budget_total_charges": Decimal(0),
                    "prev_budget_total_revenues": Decimal(0),
                    "actual_total_charges": Decimal(0),
                    "actual_total_revenues": Decimal(0),
                },
            )
            sg = mg["supergroups"].setdefault(
                sg_key,
                {
                    "label": supergroup.label,
                    "groups": {},
                    "budget_total_charges": Decimal(0),
                    "budget_total_revenues": Decimal(0),
                    "prev_budget_total_charges": Decimal(0),
                    "prev_budget_total_revenues": Decimal(0),
                    "actual_total_charges": Decimal(0),
                    "actual_total_revenues": Decimal(0),
                },
            )
            # ajout dans ag = sg["groups"].setdefault(...)
            ag = sg["groups"].setdefault(
                ag_key,
                {
                    "label": group.label,
                    "accounts": [],
                    "budget_total_charges": Decimal(0),
                    "budget_total_revenues": Decimal(0),
                    "prev_budget_total_charges": Decimal(0),
                    "prev_budget_total_revenues": Decimal(0),
                    "actual_total_charges": Decimal(0),
                    "actual_total_revenues": Decimal(0),
                    "responsible": responsibilities.get(group.id),
                },
            )

            ag["accounts"].append(account)
            ag["budget_total_charges"] += account.budget_charges
            ag["budget_total_revenues"] += account.budget_revenues
            ag["prev_budget_total_charges"] += account.prev_budget_charges
            ag["prev_budget_total_revenues"] += account.prev_budget_revenues
            ag["actual_total_charges"] += account.actual_charges
            ag["actual_total_revenues"] += account.actual_revenues

            sg["budget_total_charges"] += account.budget_charges
            sg["budget_total_revenues"] += account.budget_revenues
            sg["prev_budget_total_charges"] += account.prev_budget_charges
            sg["prev_budget_total_revenues"] += account.prev_budget_revenues
            sg["actual_total_charges"] += account.actual_charges
            sg["actual_total_revenues"] += account.actual_revenues

            mg["budget_total_charges"] += account.budget_charges
            mg["budget_total_revenues"] += account.budget_revenues
            mg["prev_budget_total_charges"] += account.prev_budget_charges
            mg["prev_budget_total_revenues"] += account.prev_budget_revenues
            mg["actual_total_charges"] += account.actual_charges
            mg["actual_total_revenues"] += account.actual_revenues

        return self.sort_grouped_structure(raw_structure)

    def build_global_summary(self, grouped: OrderedDict) -> dict:
        """
        Build a list summarizing all MetaGroups (mg) totals.
        Each entry contains label and totals for budget, prev_budget, and actuals.
        """
        summary = []
        budget_total_charges = Decimal(0)
        budget_total_revenues = Decimal(0)
        prev_budget_total_charges = Decimal(0)
        prev_budget_total_revenues = Decimal(0)
        actual_total_charges = Decimal(0)
        actual_total_revenues = Decimal(0)
        for mg_code, mg in grouped.items():
            summary.append(
                {
                    "code": mg_code,
                    "label": mg["label"],
                    "budget_total_charges": mg["budget_total_charges"],
                    "budget_total_revenues": mg["budget_total_revenues"],
                    "prev_budget_total_charges": mg["prev_budget_total_charges"],
                    "prev_budget_total_revenues": mg["prev_budget_total_revenues"],
                    "actual_total_charges": mg["actual_total_charges"],
                    "actual_total_revenues": mg["actual_total_revenues"],
                }
            )
            budget_total_charges += mg["budget_total_charges"]
            budget_total_revenues += mg["budget_total_revenues"]
            prev_budget_total_charges += mg["prev_budget_total_charges"]
            prev_budget_total_revenues += mg["prev_budget_total_revenues"]
            actual_total_charges += mg["actual_total_charges"]
            actual_total_revenues += mg["actual_total_revenues"]

        diff_budget = budget_total_revenues - budget_total_charges
        diff_prev = prev_budget_total_revenues - prev_budget_total_charges
        diff_actual = actual_total_revenues - actual_total_charges

        totals = {
            "budget_total_charges": budget_total_charges,
            "budget_total_revenues": budget_total_revenues,
            "prev_budget_total_charges": prev_budget_total_charges,
            "prev_budget_total_revenues": prev_budget_total_revenues,
            "actual_total_charges": actual_total_charges,
            "actual_total_revenues": actual_total_revenues,
            "budget_diff": diff_budget,
            "budget_prev_diff": diff_prev,
            "actual_diff": diff_actual,
            "balanced_budget": max(budget_total_charges, budget_total_revenues),
            "balanced_prev_budget": max(prev_budget_total_charges, prev_budget_total_revenues),
            "balanced_actual": max(actual_total_charges, actual_total_revenues),
        }
        return {"rows": summary, "totals": totals}
