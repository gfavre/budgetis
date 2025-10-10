from collections import OrderedDict
from typing import Any

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import FormView
from django.views.generic import TemplateView

from ..forms import AccountFilterForm
from .mixins import AccountExplorerMixin


class AccountExplorerView(LoginRequiredMixin, AccountExplorerMixin, TemplateView):
    template_name = "accounting/account_explorer.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        form = AccountFilterForm(self.request.GET or None)
        context["form"] = form

        if form.is_valid():
            year = int(form.cleaned_data["year"])
            only = form.cleaned_data.get("only_responsible", False)
            accounts = self.get_accounts(self.request.user, year, only_responsible=bool(only))
            context["grouped"] = self.build_grouped_structure(accounts)
        else:
            # breakpoint()
            context["grouped"] = OrderedDict()

        return context


class AccountPartialView(LoginRequiredMixin, AccountExplorerMixin, FormView):
    form_class = AccountFilterForm
    template_name = "accounting/partials/account_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["last_import_text"] = self.get_last_import_info(context.get("year", None))
        return context

    def form_valid(self, form):
        year = int(form.cleaned_data["year"])

        only = bool(form.cleaned_data.get("only_responsible"))
        accounts = self.get_accounts(self.request.user, year, only_responsible=only)
        grouped = self.build_grouped_structure(accounts)

        return self.render_to_response(self.get_context_data(form=form, grouped=grouped, year=year))
