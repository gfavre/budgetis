from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.shortcuts import render
from django.views import View

from ..forms import AccountAmountForm
from ..models import Account


AMOUNT_KINDS = ("charges", "revenues")


class AccountAmountEditView(LoginRequiredMixin, PermissionRequiredMixin, View):
    """
    HTMX endpoint for in-place editing of one budget account's charges or
    revenues (the `kind` URL kwarg) directly from the budget explorer table -
    only the current budget year is editable, never actuals or a prior
    year's locked budget. GET swaps the display cell (amount_cell.html) for
    an inline input (amount_edit_form.html); POST validates and saves,
    swapping back to the display cell either way - both keyed by the same
    DOM id so the cell can flip between the two without nesting issues.
    """

    permission_required = "accounting.change_account"

    def _account(self, account_id: int) -> Account:
        return get_object_or_404(Account, pk=account_id, is_budget=True)

    def _kind(self) -> str:
        kind = self.kwargs["kind"]
        if kind not in AMOUNT_KINDS:
            message = f"Unknown amount kind: {kind}"
            raise Http404(message)
        return kind

    def get(self, request, account_id, kind):
        account = self._account(account_id)
        kind = self._kind()
        form = AccountAmountForm(initial={"amount": getattr(account, kind)})
        return render(
            request, "accounting/partials/amount_edit_form.html", {"account": account, "kind": kind, "form": form}
        )

    def post(self, request, account_id, kind):
        account = self._account(account_id)
        kind = self._kind()
        form = AccountAmountForm(request.POST)
        if form.is_valid():
            setattr(account, kind, form.cleaned_data["amount"])
            account.save(update_fields=[kind, "updated_at"])
            return render(request, "accounting/partials/amount_cell.html", {"account": account, "kind": kind})
        return render(
            request,
            "accounting/partials/amount_edit_form.html",
            {"account": account, "kind": kind, "form": form},
            status=422,
        )
