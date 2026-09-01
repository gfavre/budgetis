import json

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404
from django.shortcuts import render

from budgetis.common.models import ChartScheme
from budgetis.finance.models import AvailableYear

from ..models import Account
from ..models import AccountCodeMapping
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


def _account_value(scheme, function, nature, sub_account, year, *, is_budget) -> float | None:  # noqa: PLR0913
    """None when no row exists at all for this year (data not recorded yet -
    e.g. actuals lagging behind an already-set budget), as opposed to a real
    recorded zero. The caller decides whether that should render as a gap."""
    account = Account.objects.filter(
        scheme=scheme,
        function=function,
        nature=nature,
        sub_account=sub_account,
        year=year,
        is_budget=is_budget,
    ).first()
    return float(account.absolute_value or 0) if account else None


def _pre_transition_value(origin: AccountOrigin, year: int, *, is_budget: bool) -> float | None:
    if origin.kind == MappingKind.SPLIT:
        return None
    return sum(
        (
            _account_value(ChartScheme.MCH1, function, nature, sub_account, year, is_budget=is_budget) or 0.0
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
                _account_value(
                    account.scheme, account.function, account.nature, account.sub_account, year, is_budget=False
                )
            )
            budgets.append(
                _account_value(
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


def _format_code(function: str, nature: str, sub_account: str) -> str:
    return f"{function}.{nature}" + (f".{sub_account}" if sub_account else "")


def _origin_entries(origin: AccountOrigin) -> list[dict]:
    """Code + most recent real label of each MCH1 predecessor behind an MCH2 account."""
    entries = []
    for function, nature, sub_account in origin.mch1_codes:
        last = (
            Account.objects.filter(scheme=ChartScheme.MCH1, function=function, nature=nature, sub_account=sub_account)
            .order_by("-year")
            .first()
        )
        entries.append(
            {
                "function": function,
                "nature": nature,
                "sub_account": sub_account,
                "code": _format_code(function, nature, sub_account),
                "label": last.label if last else "",
            }
        )
    return entries


def _mch2_label(function: str, nature: str, sub_account: str) -> str:
    last = (
        Account.objects.filter(scheme=ChartScheme.MCH2, function=function, nature=nature, sub_account=sub_account)
        .order_by("-year")
        .first()
    )
    return last.label if last else ""


def _with_split_destinations(entries: list[dict], current: tuple[str, str, str]) -> list[dict]:
    """
    Adds, to each origin entry, every *other* MCH2 account it also feeds - that
    fan-out is exactly why the historical amount can't be attributed to this
    one account automatically.
    """
    for entry in entries:
        other_targets = AccountCodeMapping.objects.filter(
            mch1_function=entry["function"], mch1_nature=entry["nature"], mch1_sub_account=entry["sub_account"]
        ).exclude(mch2_function=current[0], mch2_nature=current[1], mch2_sub_account=current[2])
        entry["other_targets"] = [
            {
                "code": _format_code(t.mch2_function, t.mch2_nature, t.mch2_sub_account),
                "label": _mch2_label(t.mch2_function, t.mch2_nature, t.mch2_sub_account),
            }
            for t in other_targets
        ]
    return entries


@login_required
def account_history_modal(request, account_id):
    account = get_object_or_404(Account, id=account_id)

    origin = None
    transition_year = None
    split_origins: list[dict] = []
    pre_mch2_origins: list[dict] = []
    if account.scheme == ChartScheme.MCH2:
        origin = classify_mch2_account(account.function, account.nature, account.sub_account)
        transition_year = _transition_year()
        if origin.kind == MappingKind.SPLIT:
            current = (account.function, account.nature, account.sub_account)
            split_origins = _with_split_destinations(_origin_entries(origin), current)
        elif origin.kind in (MappingKind.ONE_TO_ONE, MappingKind.MERGE):
            pre_mch2_origins = _origin_entries(origin)

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
            "split_origins": split_origins,
            "pre_mch2_origins": pre_mch2_origins,
        },
    )
