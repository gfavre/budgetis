from collections import OrderedDict
from typing import Any

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Max
from django.views.generic import FormView
from django.views.generic import TemplateView

from ..forms import AccountFilterForm
from ..models import Account
from .mixins import AccountExplorerMixin
from .mixins import BudgetExplorerMixin


class BaseAccountExplorerView(LoginRequiredMixin, TemplateView):
    """
    Abstract view providing shared logic for account and budget explorers.
    Child classes must implement get_accounts_for_year(year: int, user) -> list[Account].
    """

    template_name = ""  # defined by subclasses
    title = "Accounts"
    is_budget_view: bool = False  # surchargé dans la sous-classe

    def get_default_year(self) -> int | None:
        """Return the most recent year available for this explorer."""
        qs = Account.objects.filter(is_budget=self.is_budget_view)
        return qs.aggregate(Max("year")).get("year__max")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        form = AccountFilterForm(self.request.GET or None)
        context["form"] = form
        context["title"] = self.title

        if form.is_valid():
            year = int(form.cleaned_data["year"])
            only = form.cleaned_data.get("only_responsible", False)
        else:
            year = self.get_default_year()
            only = form.initial.get("only_responsible", True)
            if year:
                # prefill form field
                form.initial["year"] = year
                if "year" in form.fields:
                    form.fields["year"].initial = year

        if year:
            accounts = self.get_accounts_for_year(year, self.request.user, only_responsible=bool(only))
            context.update(
                {
                    "year": year,
                    "grouped": self.build_grouped_structure(accounts),
                    "last_import_text": self.get_last_import_info(year),
                }
            )
        else:
            context["grouped"] = OrderedDict()
        return context

    def get_accounts_for_year(self, year: int, user, *, only_responsible: bool):
        """Return list of accounts for the selected year (to be implemented)."""
        raise NotImplementedError("Subclasses must implement get_accounts_for_year()")  # noqa: EM101


class AccountExplorerView(AccountExplorerMixin, BaseAccountExplorerView):
    """
    Explorer view for actual accounts + budget.
    """

    template_name = "accounting/account_explorer.html"
    is_budget_view = False

    def get_accounts_for_year(self, year: int, user, *, only_responsible: bool):
        return self.get_accounts(user, year, only_responsible=only_responsible)


class BudgetExplorerView(BudgetExplorerMixin, BaseAccountExplorerView):
    """
    Identique à AccountExplorerView mais pour les budgets :
    - affiche le budget courant, le budget de l’année -1, et les comptes de l’année -2
    - conserve le même form, la même structure, les mêmes modales et les mêmes interactions HTMX
    """

    template_name = "accounting/budget_explorer.html"
    title = "Budgets"
    is_budget_view = True

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["previous_year"] = context["year"] - 1
        context["actuals_year"] = context["year"] - 2
        return context

    def get_accounts_for_year(self, year: int, user, *, only_responsible: bool):
        return self.get_accounts(user, year, only_responsible=only_responsible)


class AccountPartialView(AccountExplorerMixin, FormView):
    """
    Partial HTMX/AJAX refresh for the accounts explorer table.
    """

    form_class = AccountFilterForm
    template_name = "accounting/partials/account_list.html"

    def form_valid(self, form):
        year = int(form.cleaned_data["year"])
        only = bool(form.cleaned_data.get("only_responsible"))
        accounts = self.get_accounts(self.request.user, year, only_responsible=only)
        grouped = self.build_grouped_structure(accounts)
        context = self.get_context_data(
            form=form,
            grouped=grouped,
            year=year,
            last_import_text=self.get_last_import_info(year),
        )
        return self.render_to_response(context)


class BudgetPartialView(BudgetExplorerMixin, FormView):
    """
    Partial HTMX/AJAX refresh for the budget explorer table.
    """

    form_class = AccountFilterForm
    template_name = "accounting/partials/budget_list.html"

    def form_valid(self, form):
        year = int(form.cleaned_data["year"])
        only = bool(form.cleaned_data.get("only_responsible"))
        accounts = self.get_accounts(self.request.user, year, only_responsible=only)
        grouped = self.build_grouped_structure(accounts)
        context = self.get_context_data(
            form=form,
            grouped=grouped,
            year=year,
            previous_year=year - 1,
            actuals_year=year - 2,
            last_import_text=self.get_last_import_info(year),
        )
        return self.render_to_response(context)
