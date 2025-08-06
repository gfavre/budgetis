from django.shortcuts import get_object_or_404
from django.shortcuts import render

from ..models import Account


def account_history_modal(request, account_id):
    account = get_object_or_404(Account, id=account_id)

    # même code de recherche que précédemment
    qs = Account.objects.filter(
        function=account.function,
        nature=account.nature,
        sub_account=account.sub_account,
    ).order_by("year")

    years = sorted(set(a.year for a in qs))  # noqa: C401
    comptes = []
    budgets = []

    for year in years:
        actual = next((a for a in qs if a.year == year and not a.is_budget), None)
        budget = next((a for a in qs if a.year == year and a.is_budget), None)

        comptes.append(float(actual.charges or 0) if actual else 0)
        budgets.append(float(budget.charges or 0) if budget else 0)

    return render(
        request,
        "accounting/partials/account_history_modal.html",
        {
            "account": account,
            "years": years,
            "comptes": comptes,
            "budgets": budgets,
        },
    )
