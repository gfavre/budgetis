import json

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404
from django.shortcuts import render

from budgetis.common.models import ChartScheme
from budgetis.finance.models import AvailableYear

from ..models import Account
from ..models import AccountComment
from ..scheme_transition import AccountOrigin
from ..scheme_transition import MappingKind
from ..scheme_transition import classify_mch2_account
from ..scheme_transition import first_mch2_year


def _transition_year() -> int | None:
    known_years = [
        year
        for year in (
            first_mch2_year(AvailableYear.YearType.BUDGET),
            first_mch2_year(AvailableYear.YearType.ACTUAL),
        )
        if year is not None
    ]
    return min(known_years) if known_years else None


def _actual_value(scheme, function, nature, sub_account, year, *, is_budget) -> float:  # noqa: PLR0913
    account = Account.objects.filter(
        scheme=scheme,
        function=function,
        nature=nature,
        sub_account=sub_account,
        year=year,
        is_budget=is_budget,
    ).first()
    return float(account.absolute_value or 0) if account else 0.0


def _pre_transition_value(origin: AccountOrigin, year: int, *, is_budget: bool) -> float | None:
    if origin.kind == MappingKind.SPLIT:
        return None
    return sum(
        (
            _actual_value(ChartScheme.MCH1, function, nature, sub_account, year, is_budget=is_budget)
            for function, nature, sub_account in origin.mch1_codes
        ),
        start=0.0,
    )


def _series(
    account: Account, origin: AccountOrigin | None, transition_year: int | None, years: list[int]
) -> tuple[list, list]:
    comptes = []
    budgets = []
    for year in years:
        if origin is not None and transition_year is not None and year < transition_year:
            comptes.append(_pre_transition_value(origin, year, is_budget=False))
            budgets.append(_pre_transition_value(origin, year, is_budget=True))
        else:
            comptes.append(
                _actual_value(
                    account.scheme, account.function, account.nature, account.sub_account, year, is_budget=False
                )
            )
            budgets.append(
                _actual_value(
                    account.scheme, account.function, account.nature, account.sub_account, year, is_budget=True
                )
            )
    return comptes, budgets


def _history_years(account: Account) -> list[int]:
    if account.scheme == ChartScheme.MCH2:
        # A stable axis (not just this account's own years) so a split account
        # still shows its pre-transition years as a visible gap.
        return sorted(AvailableYear.objects.values_list("year", flat=True).distinct())
    return sorted(
        Account.objects.filter(
            scheme=account.scheme,
            function=account.function,
            nature=account.nature,
            sub_account=account.sub_account,
        )
        .values_list("year", flat=True)
        .distinct()
    )


def _origin_labels(origin: AccountOrigin) -> list[str]:
    labels = []
    for function, nature, sub_account in origin.mch1_codes:
        last = (
            Account.objects.filter(scheme=ChartScheme.MCH1, function=function, nature=nature, sub_account=sub_account)
            .order_by("-year")
            .first()
        )
        code = f"{function}.{nature}" + (f".{sub_account}" if sub_account else "")
        labels.append(f"{code} - {last.label}" if last else code)
    return labels


@login_required
def account_history_modal(request, account_id):
    account = get_object_or_404(Account, id=account_id)

    origin = None
    transition_year = None
    origin_labels: list[str] = []
    if account.scheme == ChartScheme.MCH2:
        origin = classify_mch2_account(account.function, account.nature, account.sub_account)
        transition_year = _transition_year()
        if origin.kind == MappingKind.SPLIT:
            origin_labels = _origin_labels(origin)

    years = _history_years(account)
    comptes, budgets = _series(account, origin, transition_year, years)

    comments = AccountComment.objects.filter(
        account__scheme=account.scheme,
        account__function=account.function,
        account__nature=account.nature,
        account__sub_account=account.sub_account,
    ).select_related("account")

    comments_by_year: dict[int, dict[str, list[str]]] = {}
    for comment in comments:
        year = comment.account.year
        key = "budget" if comment.account.is_budget else "comptes"
        comments_by_year.setdefault(year, {}).setdefault(key, []).append(comment.content)

    return render(
        request,
        "accounting/partials/account_history_modal.html",
        {
            "account": account,
            "years": json.dumps(years),
            "comptes": json.dumps(comptes),
            "budgets": json.dumps(budgets),
            "comments_by_year": json.dumps(comments_by_year),
            "transition_year": transition_year,
            "origin_labels": origin_labels,
        },
    )
