import json

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404
from django.shortcuts import render

from ..models import Account
from ..models import AccountComment


@login_required
def account_history_modal(request, account_id):
    account = get_object_or_404(Account, id=account_id)

    # même code de recherche que précédemment
    qs = Account.objects.filter(
        function=account.function,
        nature=account.nature,
        sub_account=account.sub_account,
    ).order_by("year")
    comments = AccountComment.objects.filter(
        account__function=account.function, account__nature=account.nature, account__sub_account=account.sub_account
    ).select_related("account")

    years = sorted(set(a.year for a in qs))  # noqa: C401
    comptes = []
    budgets = []

    comments_by_year = {}
    for c in comments:
        year = c.account.year
        key = "budget" if c.account.is_budget else "comptes"
        comments_by_year.setdefault(year, {}).setdefault(key, []).append(c.content)

    for year in years:
        actual = next((a for a in qs if a.year == year and not a.is_budget), None)
        budget = next((a for a in qs if a.year == year and a.is_budget), None)

        comptes.append(float(actual.absolute_value or 0) if actual else 0)
        budgets.append(float(budget.absolute_value or 0) if budget else 0)

    return render(
        request,
        "accounting/partials/account_history_modal.html",
        {
            "account": account,
            "years": years,
            "comptes": comptes,
            "budgets": budgets,
            "comments_by_year": json.dumps(comments_by_year),
        },
    )
