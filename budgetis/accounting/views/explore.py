from collections import OrderedDict
from typing import TYPE_CHECKING
from typing import Any
from typing import cast
from urllib.parse import urlencode

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Max
from django.http import HttpRequest
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.generic import FormView
from django.views.generic import TemplateView

from budgetis.accounting.groupers import build_grouped
from budgetis.accounting.groupers import build_nature_grouped
from budgetis.accounting.groupers import build_nature_tree
from budgetis.accounting.groupers import build_summary
from budgetis.accounting.loaders import ActualsLoader
from budgetis.accounting.loaders import BudgetLoader
from budgetis.accounting.loaders import get_last_import_info
from budgetis.accounting.models import Account
from budgetis.accounting.scheme_transition import comparison_flags
from budgetis.accounting.staged_result import build_staged_result
from budgetis.accounting.staged_result import staged_comparison_flags

from ..forms import AccountFilterForm
from ..forms import NatureFilterForm
from ..forms import YearFilterForm


if TYPE_CHECKING:
    from budgetis.users.models import User


# FormMixin only in a TYPE_CHECKING branch: needed so mypy knows the
# `super().get_form_kwargs()` this mixin calls actually exists on whatever
# FormView subclass it's combined with, without making it a real base class
# that would fight for a slot in the runtime MRO.
if TYPE_CHECKING:
    from django.views.generic.edit import FormMixin as _UserFormKwargsBase
else:
    _UserFormKwargsBase = object


class UserFormKwargsMixin(_UserFormKwargsBase):
    """Passes the logged-in user to the form so AccountFilterForm can hide "only my accounts" for non-municipals."""

    request: HttpRequest  # set by View.setup() at runtime; declared here only for mypy

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs


class BaseExplorerView(LoginRequiredMixin, TemplateView):
    """
    Base view for all account/budget explorers.
    Subclasses set loader_class and implement _extra_context().
    """

    template_name = ""
    title = ""
    is_budget_view: bool = False
    loader_class: type[ActualsLoader | BudgetLoader] = ActualsLoader
    form_class: type[AccountFilterForm | YearFilterForm] = AccountFilterForm

    def _get_default_year(self) -> int | None:
        return Account.objects.filter(is_budget=self.is_budget_view).aggregate(Max("year")).get("year__max")

    def _extra_context(self, year: int) -> dict[str, Any]:
        return {}

    def _build(self, year: int, user, *, only_responsible: bool, detail: bool = False) -> dict[str, Any]:
        loader = self.loader_class()
        rows = loader.load(year, user, only_responsible=only_responsible)
        grouped = build_grouped(rows, year)
        return {
            "grouped": grouped,
            "global_summary": build_summary(grouped),
            "last_import_text": get_last_import_info(year),
        }

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        form = self.form_class(self.request.GET or None, user=self.request.user)
        context["form"] = form
        context["title"] = self.title

        if form.is_valid():
            year = int(form.cleaned_data["year"])
            only = form.cleaned_data.get("only_responsible", False)
            detail = form.cleaned_data.get("detail", False)
        else:
            year = self._get_default_year()
            only = form.initial.get("only_responsible", True)
            detail = form.initial.get("detail", False)
            if year:
                form.initial["year"] = year
                if "year" in form.fields:
                    form.fields["year"].initial = year

        # A non-municipal user has no "own accounts" to speak of - see
        # AccountFilterForm's docstring - so this holds regardless of what
        # the (hidden, for them) checkbox or query string says.
        only = bool(only) and cast("User", self.request.user).is_municipal

        if year:
            context.update(self._build(year, self.request.user, only_responsible=only, detail=bool(detail)))
            context["year"] = year
            context.update(comparison_flags(year, is_budget=self.is_budget_view))
            context.update(self._extra_context(year))
        else:
            context["grouped"] = OrderedDict()

        return context


class AccountExplorerView(BaseExplorerView):
    template_name = "accounting/account_explorer.html"
    title = _("Actuals")
    is_budget_view = False
    loader_class = ActualsLoader


class BudgetExplorerView(BaseExplorerView):
    template_name = "accounting/budget_explorer.html"
    title = _("Budgets")
    is_budget_view = True
    loader_class = BudgetLoader

    def _extra_context(self, year: int) -> dict[str, Any]:
        return {"previous_year": year - 1, "actuals_year": year - 2}


def _explorer_push_url(url_name: str, *, year: int, only_responsible: bool) -> str:
    """
    URL htmx should push into browser history after a filter change, so a
    reload, bookmark, or shared link reproduces the same year and "only my
    accounts" state - BaseExplorerView.get_context_data already reads both
    from the query string on a plain GET; this just keeps the address bar in
    sync with what the htmx-swapped list is actually showing.
    """
    params: dict[str, int | str] = {"year": year}
    if only_responsible:
        params["only_responsible"] = "on"
    return f"{reverse(f'accounting:{url_name}')}?{urlencode(params)}"


class AccountPartialView(UserFormKwargsMixin, LoginRequiredMixin, FormView):
    form_class = AccountFilterForm
    template_name = "accounting/partials/account_list.html"

    def form_valid(self, form):
        year = int(form.cleaned_data["year"])
        only = bool(form.cleaned_data.get("only_responsible")) and cast("User", self.request.user).is_municipal
        rows = ActualsLoader().load(year, self.request.user, only_responsible=only)
        grouped = build_grouped(rows, year)
        response = self.render_to_response(
            self.get_context_data(
                form=form,
                grouped=grouped,
                global_summary=build_summary(grouped),
                year=year,
                last_import_text=get_last_import_info(year),
                **comparison_flags(year, is_budget=False),
            )
        )
        response["HX-Push-Url"] = _explorer_push_url("account-explorer", year=year, only_responsible=only)
        return response


class BudgetPartialView(UserFormKwargsMixin, LoginRequiredMixin, FormView):
    form_class = AccountFilterForm
    template_name = "accounting/partials/budget_list.html"

    def form_valid(self, form):
        year = int(form.cleaned_data["year"])
        only = bool(form.cleaned_data.get("only_responsible")) and cast("User", self.request.user).is_municipal
        rows = BudgetLoader().load(year, self.request.user, only_responsible=only)
        grouped = build_grouped(rows, year)
        response = self.render_to_response(
            self.get_context_data(
                form=form,
                grouped=grouped,
                global_summary=build_summary(grouped),
                year=year,
                previous_year=year - 1,
                actuals_year=year - 2,
                last_import_text=get_last_import_info(year),
                **comparison_flags(year, is_budget=True),
            )
        )
        response["HX-Push-Url"] = _explorer_push_url("budget-explorer", year=year, only_responsible=only)
        return response


class BudgetByNatureView(BaseExplorerView):
    template_name = "accounting/budget_by_nature.html"
    title = _("Budget by nature")
    is_budget_view = True
    loader_class = BudgetLoader
    form_class = NatureFilterForm

    def _extra_context(self, year: int) -> dict[str, Any]:
        return {"previous_year": year - 1, "actuals_year": year - 2}

    def _build(self, year: int, user, *, only_responsible: bool, detail: bool = False) -> dict[str, Any]:
        rows = self.loader_class().load(year, user, only_responsible=False)
        grouped = build_nature_grouped(rows)
        return {
            "grouped": grouped,
            "nature_tree": build_nature_tree(rows),
            "detail": detail,
            "global_summary": build_summary(grouped),
            "last_import_text": get_last_import_info(year),
        }


class BudgetByNaturePartialView(LoginRequiredMixin, FormView):
    form_class = NatureFilterForm
    template_name = "accounting/partials/budget_by_nature_list.html"

    def form_valid(self, form):
        year = int(form.cleaned_data["year"])
        rows = BudgetLoader().load(year, self.request.user, only_responsible=False)
        grouped = build_nature_grouped(rows)
        return self.render_to_response(
            self.get_context_data(
                form=form,
                grouped=grouped,
                nature_tree=build_nature_tree(rows),
                detail=bool(form.cleaned_data.get("detail")),
                global_summary=build_summary(grouped),
                year=year,
                previous_year=year - 1,
                actuals_year=year - 2,
                last_import_text=get_last_import_info(year),
                **comparison_flags(year, is_budget=True),
            )
        )


class AccountByNatureView(BaseExplorerView):
    template_name = "accounting/account_by_nature.html"
    title = _("Actuals by nature")
    is_budget_view = False
    loader_class = ActualsLoader
    form_class = NatureFilterForm

    def _extra_context(self, year: int) -> dict[str, Any]:
        return {"prev_year": year - 1}

    def _build(self, year: int, user, *, only_responsible: bool, detail: bool = False) -> dict[str, Any]:
        rows = self.loader_class().load(year, user, only_responsible=False)
        grouped = build_nature_grouped(rows)
        return {
            "grouped": grouped,
            "nature_tree": build_nature_tree(rows),
            "detail": detail,
            "global_summary": build_summary(grouped),
            "last_import_text": get_last_import_info(year),
        }


class AccountByNaturePartialView(LoginRequiredMixin, FormView):
    form_class = NatureFilterForm
    template_name = "accounting/partials/account_by_nature_list.html"

    def form_valid(self, form):
        year = int(form.cleaned_data["year"])
        rows = ActualsLoader().load(year, self.request.user, only_responsible=False)
        grouped = build_nature_grouped(rows)
        return self.render_to_response(
            self.get_context_data(
                form=form,
                grouped=grouped,
                nature_tree=build_nature_tree(rows),
                detail=bool(form.cleaned_data.get("detail")),
                global_summary=build_summary(grouped),
                year=year,
                prev_year=year - 1,
                last_import_text=get_last_import_info(year),
                **comparison_flags(year, is_budget=False),
            )
        )


class BudgetStagedResultView(BaseExplorerView):
    template_name = "accounting/budget_staged_result.html"
    title = _("Budget - staged result")
    is_budget_view = True
    form_class = YearFilterForm

    def _extra_context(self, year: int) -> dict[str, Any]:
        return {"previous_year": year - 1, "actuals_year": year - 2, **staged_comparison_flags(year, is_budget=True)}

    def _build(self, year: int, user, *, only_responsible: bool, detail: bool = False) -> dict[str, Any]:
        columns = [(year, True), (year - 1, True), (year - 2, False)]
        return {
            "tiers": build_staged_result(columns),
            "last_import_text": get_last_import_info(year),
        }


class BudgetStagedResultPartialView(LoginRequiredMixin, FormView):
    form_class = YearFilterForm
    template_name = "accounting/partials/staged_result_list.html"

    def form_valid(self, form):
        year = int(form.cleaned_data["year"])
        columns = [(year, True), (year - 1, True), (year - 2, False)]
        return self.render_to_response(
            self.get_context_data(
                tiers=build_staged_result(columns),
                last_import_text=get_last_import_info(year),
                is_budget_view=True,
                col1_year=year,
                col2_year=year - 1,
                col3_year=year - 2,
                **staged_comparison_flags(year, is_budget=True),
            )
        )


class AccountStagedResultView(BaseExplorerView):
    template_name = "accounting/account_staged_result.html"
    title = _("Actuals - staged result")
    is_budget_view = False
    form_class = YearFilterForm

    def _extra_context(self, year: int) -> dict[str, Any]:
        return {"prev_year": year - 1, **staged_comparison_flags(year, is_budget=False)}

    def _build(self, year: int, user, *, only_responsible: bool, detail: bool = False) -> dict[str, Any]:
        columns = [(year, False), (year, True), (year - 1, False)]
        return {
            "tiers": build_staged_result(columns),
            "last_import_text": get_last_import_info(year),
        }


class AccountStagedResultPartialView(LoginRequiredMixin, FormView):
    form_class = YearFilterForm
    template_name = "accounting/partials/staged_result_list.html"

    def form_valid(self, form):
        year = int(form.cleaned_data["year"])
        columns = [(year, False), (year, True), (year - 1, False)]
        return self.render_to_response(
            self.get_context_data(
                tiers=build_staged_result(columns),
                last_import_text=get_last_import_info(year),
                is_budget_view=False,
                col1_year=year,
                col2_year=year,
                col3_year=year - 1,
                **staged_comparison_flags(year, is_budget=False),
            )
        )
