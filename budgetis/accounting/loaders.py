from decimal import Decimal

from django.db.models import Count
from django.utils import formats
from django.utils.translation import gettext_lazy as _

from budgetis.accounting.models import Account
from budgetis.accounting.models import GroupResponsibility
from budgetis.accounting.views.data import AccountRow
from budgetis.bdi_import.models import AccountImportLog


def get_last_import_info(year: int) -> str:
    """Return a human-readable string with the last import dates for budget and actual accounts."""

    def _get_date(*, is_budget: bool) -> str | None:
        log = (
            AccountImportLog.objects.filter(year=year, is_budget=is_budget, status="success")
            .order_by("-created_at")
            .first()
        )
        return formats.date_format(log.created_at, "j F Y") if log else None

    budget_date = _get_date(is_budget=True)
    actual_date = _get_date(is_budget=False)

    if not budget_date and not actual_date:
        return ""
    parts = []
    if budget_date:
        parts.append(f"{budget_date} ({_('budget')})")
    if actual_date:
        parts.append(f"{actual_date} ({_('actuals')})")
    return str(_("Last import:")) + " " + "  •  ".join(parts)


class BaseLoader:
    """Shared ORM helpers for ActualsLoader and BudgetLoader."""

    def _get_group_ids(self, user, year: int, *, only_responsible: bool) -> list[int]:
        if not only_responsible:
            return []
        return list(GroupResponsibility.objects.filter(year=year, responsible=user).values_list("group_id", flat=True))

    def _get_accounts_queryset(self, year: int, *, is_budget: bool, group_ids: list[int] | None = None):
        qs = (
            Account.objects.filter(year=year, is_budget=is_budget, group__isnull=False, visible_in_report=True)
            .select_related("group__supergroup__metagroup")
            .prefetch_related("comments")
            .annotate(comment_count=Count("comments"))
        )
        if group_ids:
            qs = qs.filter(group__in=group_ids)
        return qs


class ActualsLoader(BaseLoader):
    """
    Loads accounts for the actuals explorer.

    col1 = actuals N   col2 = budget N   col3 = actuals N-1
    """

    def load(self, year: int, user, *, only_responsible: bool) -> list[AccountRow]:
        group_ids = self._get_group_ids(user, year, only_responsible=only_responsible)
        accounts = list(self._get_accounts_queryset(year, is_budget=False, group_ids=group_ids or None))

        if not accounts:
            return self._budget_fallback(year, group_ids)

        self._attach_budget(year, accounts)
        self._ensure_budget_defaults(accounts)
        self._attach_prev_actuals(year, accounts)

        return [
            AccountRow(
                account=acc,
                col1_charges=acc.charges,
                col1_revenues=acc.revenues,
                col2_charges=acc.budget_charges,
                col2_revenues=acc.budget_revenues,
                col3_charges=acc.prev_actual_charges,
                col3_revenues=acc.prev_actual_revenues,
            )
            for acc in accounts
        ]

    def _budget_fallback(self, year: int, group_ids: list[int]) -> list[AccountRow]:
        qs = (
            Account.objects.filter(year=year, is_budget=True, group__isnull=False)
            .select_related("group__supergroup__metagroup")
            .annotate(comment_count=Count("comments"))
        )
        if group_ids:
            qs = qs.filter(group__in=group_ids)

        rows = []
        for acc in qs:
            acc.budget_id = acc.id
            acc.budget_comment_count = acc.comment_count
            rows.append(
                AccountRow(
                    account=acc,
                    col2_charges=acc.charges,
                    col2_revenues=acc.revenues,
                )
            )
        return rows

    def _attach_budget(self, year: int, accounts: list[Account]) -> None:
        keys = {(a.function, a.nature, a.sub_account): a for a in accounts}
        budget_qs = Account.objects.filter(
            year=year,
            is_budget=True,
            function__in=[k[0] for k in keys],
            nature__in=[k[1] for k in keys],
        ).annotate(comment_count=Count("comments"))

        for b in budget_qs:
            actual = keys.get((b.function, b.nature, b.sub_account))
            if actual:
                actual.budget_charges = b.charges
                actual.budget_revenues = b.revenues
                actual.budget_id = b.id
                actual.budget_comment_count = b.comment_count  # type: ignore[attr-defined]

    def _ensure_budget_defaults(self, accounts: list[Account]) -> None:
        for acc in accounts:
            if not hasattr(acc, "budget_charges"):
                acc.budget_charges = Decimal("0.00")
            if not hasattr(acc, "budget_revenues"):
                acc.budget_revenues = Decimal("0.00")
            if not hasattr(acc, "budget_id"):
                acc.budget_id = None
            if not hasattr(acc, "budget_comment_count"):
                acc.budget_comment_count = 0

    def _attach_prev_actuals(self, year: int, accounts: list[Account]) -> None:
        prev_qs = Account.objects.filter(
            year=year - 1,
            is_budget=False,
            function__in=[a.function for a in accounts],
            nature__in=[a.nature for a in accounts],
        ).annotate(comment_count=Count("comments"))
        prev_map = {(a.function, a.nature, a.sub_account): a for a in prev_qs}
        for acc in accounts:
            prev = prev_map.get((acc.function, acc.nature, acc.sub_account))
            acc.prev_actual_charges = prev.charges if prev else Decimal("0.00")
            acc.prev_actual_revenues = prev.revenues if prev else Decimal("0.00")
            acc.prev_actual_id = prev.id if prev else None
            acc.prev_actual_comment_count = prev.comment_count if prev else 0


class BudgetLoader(BaseLoader):
    """
    Loads accounts for the budget explorer.

    col1 = budget N   col2 = budget N-1   col3 = actuals N-2
    """

    def load(self, year: int, user, *, only_responsible: bool) -> list[AccountRow]:
        group_ids = self._get_group_ids(user, year, only_responsible=only_responsible)
        current = list(self._get_accounts_queryset(year, is_budget=True, group_ids=group_ids or None))
        prev = list(self._get_accounts_queryset(year - 1, is_budget=True))
        actuals = list(self._get_accounts_queryset(year - 2, is_budget=False))

        prev_map = {(a.function, a.nature, a.sub_account): a for a in prev}
        act_map = {(a.function, a.nature, a.sub_account): a for a in actuals}

        rows = []
        for acc in current:
            key = (acc.function, acc.nature, acc.sub_account)
            p = prev_map.get(key)
            a = act_map.get(key)
            acc.budget_id = acc.id
            acc.budget_comment_count = acc.comment_count or 0  # type: ignore[attr-defined]
            acc.actuals_id = a.id if a else None
            acc.actuals_comment_count = a.comment_count if a else 0
            rows.append(
                AccountRow(
                    account=acc,
                    col1_charges=acc.charges,
                    col1_revenues=acc.revenues,
                    col2_charges=p.charges if p else Decimal("0.00"),
                    col2_revenues=p.revenues if p else Decimal("0.00"),
                    col3_charges=a.charges if a else Decimal("0.00"),
                    col3_revenues=a.revenues if a else Decimal("0.00"),
                )
            )
        return rows
