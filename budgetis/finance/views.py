from __future__ import annotations

from typing import Any

from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.db.models import Prefetch
from django.forms import modelform_factory
from django.http import Http404
from django.http import HttpResponse
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.shortcuts import render
from django.views import View
from django.views.generic import CreateView
from django.views.generic import TemplateView
from django.views.generic import UpdateView

from budgetis.accounting.models import Account
from budgetis.common.models import ChartScheme

from .builders import build_income_budget_canton_intercos_commune
from .builders import build_sankeymatic_export
from .models import AvailableYear
from .models import SankeyAccountCodeRule
from .models import SankeyCategory
from .models import SankeyFlow
from .models import SankeyFunctionNatureRule
from .models import SankeyLabelRule
from .models import SankeyNatureRangeRule


# One entry per editable rule type, keyed by the URL slug used for it. Lets
# SankeyRuleCreateView/SankeyRuleUpdateView stay generic (one pair of views
# for all four rule models) instead of four near-identical view classes.
RULE_TYPES: dict[str, dict[str, Any]] = {
    "nature-range": {
        "model": SankeyNatureRangeRule,
        "fields": ["nature_start", "nature_end", "priority"],
        "ordering": ("priority", "nature_start"),
        "rows_template": "finance/partials/rule_rows_nature_range.html",
    },
    "function-nature": {
        "model": SankeyFunctionNatureRule,
        "fields": ["function_prefix", "nature_start", "nature_end"],
        "ordering": ("function_prefix", "nature_start"),
        "rows_template": "finance/partials/rule_rows_function_nature.html",
    },
    "account-code": {
        "model": SankeyAccountCodeRule,
        "fields": ["function", "nature", "sub_account"],
        "ordering": ("function", "nature"),
        "rows_template": "finance/partials/rule_rows_account_code.html",
    },
    "label": {
        "model": SankeyLabelRule,
        "fields": ["pattern"],
        "ordering": ("pattern",),
        "rows_template": "finance/partials/rule_rows_label.html",
    },
}


def _scheme_for(qs) -> str:
    """Accounts for a given (year, is_budget) are homogeneous in scheme; default to MCH1 if empty."""
    first = qs.values_list("scheme", flat=True).first()
    return first or ChartScheme.MCH1


def _default_scheme() -> str:
    latest = AvailableYear.objects.order_by("-year").values_list("scheme", flat=True).first()
    return latest or ChartScheme.MCH2


# Display order for the Sankey config page - matches the diagram's own
# left-to-right flow (Revenue -> Household -> Canton/Intercos/Commune ->
# Dotation), not SankeyCategory's default alphabetical-by-flow ordering.
_FLOW_DISPLAY_ORDER = (
    SankeyFlow.REVENUE,
    SankeyFlow.CANTON,
    SankeyFlow.INTERCOMMUNALITY,
    SankeyFlow.COMMUNE,
    SankeyFlow.DOTATION,
)


def _categories_grouped_by_flow(scheme: str) -> list[dict[str, Any]]:
    """
    Every Sankey category for `scheme`, with its rules of each type
    (scheme-filtered) attached, grouped by flow in diagram order. Categories
    with no rule at all for this scheme are still included, so a gap in
    coverage is visible rather than silently missing from the page.
    """
    categories = SankeyCategory.objects.prefetch_related(
        Prefetch(
            "nature_range_rules",
            queryset=SankeyNatureRangeRule.objects.filter(scheme=scheme).order_by("priority", "nature_start"),
            to_attr="nature_range_rules_for_scheme",
        ),
        Prefetch(
            "function_nature_rules",
            queryset=SankeyFunctionNatureRule.objects.filter(scheme=scheme).order_by(
                "function_prefix", "nature_start"
            ),
            to_attr="function_nature_rules_for_scheme",
        ),
        Prefetch(
            "account_code_rules",
            queryset=SankeyAccountCodeRule.objects.filter(scheme=scheme).order_by("function", "nature"),
            to_attr="account_code_rules_for_scheme",
        ),
        Prefetch(
            "label_rules",
            queryset=SankeyLabelRule.objects.filter(scheme=scheme).order_by("pattern"),
            to_attr="label_rules_for_scheme",
        ),
    ).order_by("flow", "order")

    by_flow: dict[str, list[SankeyCategory]] = {flow: [] for flow in _FLOW_DISPLAY_ORDER}
    for category in categories:
        by_flow[category.flow].append(category)

    return [
        {"flow": flow, "flow_label": SankeyFlow(flow).label, "categories": by_flow[flow]}
        for flow in _FLOW_DISPLAY_ORDER
        if by_flow[flow]
    ]


class SankeyDataView(LoginRequiredMixin, View):
    """
    Return Sankey data (nodes/links) as JSON for the requested parameters.

    Query params:
        year: int (required)
        is_budget: "1" or "0" (default "0")
    """

    def get(self, request, *args, **kwargs) -> JsonResponse:
        year_str = request.GET.get("year", "")
        if not year_str.isdigit():
            return JsonResponse({"error": "Missing or invalid 'year'."}, status=400)
        budget_str = request.GET.get("budget", "false").lower()
        budget = budget_str in ("true", "1", "yes", "on")
        year = int(year_str)
        qs = Account.objects.filter(year=year, is_budget=budget)
        data: dict[str, Any] = build_income_budget_canton_intercos_commune(qs, _scheme_for(qs))
        return JsonResponse(data, safe=False)


class SankeyView(LoginRequiredMixin, TemplateView):
    template_name = "finance/sankey.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # A year's scheme is consistent across its Budget/Actual rows (see
        # AvailableYear) - keep the first (most recent) one seen per year.
        years_by_year: dict[int, str] = {}
        for row in AvailableYear.objects.order_by("-year").values("year", "scheme"):
            years_by_year.setdefault(row["year"], row["scheme"])
        available_years = [{"year": year, "scheme": scheme} for year, scheme in years_by_year.items()]

        actual_years = list(
            AvailableYear.objects.filter(type=AvailableYear.YearType.ACTUAL)
            .order_by("-year")
            .values_list("year", flat=True)
        )
        default_year = actual_years[0] if actual_years else (available_years[0]["year"] if available_years else None)
        context["available_years"] = available_years
        context["default_year"] = default_year
        return context


class SankeyRulesView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    """
    Overview, per scheme, of how each Sankey category is built: its
    nature-range, function+nature, exact-code and label rules. Reachable
    from the Sankey page, pre-filtered to whichever scheme the selected year
    uses. Restricted to finance staff - grant the "finance | Sankey category
    | Can view" permission (e.g. via a "Bourse" group in the admin) to the
    relevant users, rather than a new field on User.

    Each rule and each category is editable in place via SankeyRuleCreateView/
    SankeyRuleUpdateView/SankeyCategoryEditView, using the same HTMX-modal +
    out-of-band-refresh pattern as accounting's comment editing (see
    accounting/views/comments.py) - not a redirect to Django admin. Editing
    additionally requires the "finance | Sankey category | Can change"
    permission, used as a single blanket edit permission for all four rule
    types rather than one permission per model.
    """

    template_name = "finance/sankey_rules.html"
    permission_required = "finance.view_sankeycategory"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        scheme = self.request.GET.get("scheme")
        if scheme not in ChartScheme.values:
            scheme = _default_scheme()
        context["scheme"] = scheme
        context["scheme_display"] = dict(ChartScheme.choices).get(scheme, scheme)
        context["other_scheme"] = ChartScheme.MCH2 if scheme == ChartScheme.MCH1 else ChartScheme.MCH1
        context["flow_groups"] = _categories_grouped_by_flow(scheme)
        return context


def _bootstrap_styled(form):
    """
    Add Bootstrap classes to every field's widget. These forms are built
    dynamically via modelform_factory (RULE_TYPES) or a plain `fields = [...]`
    list (SankeyCategoryEditView) rather than declared with widgets up front
    like AccountCommentForm, so there's nowhere else to put the classes.
    """
    for field in form.fields.values():
        css_class = "form-control-color" if getattr(field.widget, "input_type", None) == "color" else "form-control"
        field.widget.attrs["class"] = css_class
    return form


def _rule_type_config(rule_type: str) -> dict[str, Any]:
    config = RULE_TYPES.get(rule_type)
    if config is None:
        message = f"Unknown Sankey rule type: {rule_type}"
        raise Http404(message)
    return config


def _render_rule_rows_oob(request, rule_type: str, category: SankeyCategory, scheme: str) -> HttpResponse:
    """
    Full refresh of one rule-type's table body for one category, as an
    out-of-band HTMX response. A full re-render (rather than patching just
    the added/edited row) is simplest and is the only way an OOB swap can
    make a previously-empty table stop being empty - there's no row element
    inside it yet to target.
    """
    config = _rule_type_config(rule_type)
    rules = config["model"].objects.filter(scheme=scheme, category=category).order_by(*config["ordering"])
    html = render(
        request,
        config["rows_template"],
        {"rules": rules, "category": category, "rule_type": rule_type, "scheme": scheme, "oob": True},
    )
    html["HX-Trigger"] = "closeSankeyRuleModal"
    return html


class SankeyRuleCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    """
    HTMX endpoint: GET returns a blank add-form rendered into the shared
    modal on the Sankey config page; POST validates and saves it. On
    success, returns the whole rule-type table for that category as an
    out-of-band swap (see _render_rule_rows_oob) instead of a redirect, and
    triggers the modal to close - see static/js/project.js. Handles all four
    rule types (the `rule_type` URL kwarg) rather than needing one view per
    type - see RULE_TYPES.
    """

    template_name = "finance/partials/sankey_rule_form.html"
    permission_required = "finance.change_sankeycategory"

    def get_form_class(self):
        config = _rule_type_config(self.kwargs["rule_type"])
        return modelform_factory(config["model"], fields=config["fields"])

    def get_form(self, form_class=None):
        return _bootstrap_styled(super().get_form(form_class))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["rule_type"] = self.kwargs["rule_type"]
        context["scheme"] = self.request.GET.get("scheme", "")
        context["category"] = get_object_or_404(SankeyCategory, pk=self.kwargs["category_id"])
        context["is_create"] = True
        return context

    def form_valid(self, form):
        category = get_object_or_404(SankeyCategory, pk=self.kwargs["category_id"])
        scheme = self.request.GET.get("scheme", "")
        form.instance.category = category
        form.instance.scheme = scheme
        form.save()
        return _render_rule_rows_oob(self.request, self.kwargs["rule_type"], category, scheme)


class SankeyRuleUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    """Same as SankeyRuleCreateView, but editing an existing rule - see its docstring."""

    template_name = "finance/partials/sankey_rule_form.html"
    permission_required = "finance.change_sankeycategory"

    def get_form_class(self):
        config = _rule_type_config(self.kwargs["rule_type"])
        return modelform_factory(config["model"], fields=config["fields"])

    def get_form(self, form_class=None):
        return _bootstrap_styled(super().get_form(form_class))

    def get_queryset(self):
        return _rule_type_config(self.kwargs["rule_type"])["model"].objects.all()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["rule_type"] = self.kwargs["rule_type"]
        context["scheme"] = self.request.GET.get("scheme", "")
        context["category"] = self.object.category
        context["is_create"] = False
        return context

    def form_valid(self, form):
        rule = form.save()
        scheme = self.request.GET.get("scheme", "")
        return _render_rule_rows_oob(self.request, self.kwargs["rule_type"], rule.category, scheme)


class SankeyCategoryEditView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    """
    HTMX endpoint editing a category's name/color/order - not its flow,
    since moving a category to a different hub is a bigger structural change
    than this quick-edit form is meant for. Same modal + OOB-refresh pattern
    as the rule views above.
    """

    model = SankeyCategory
    fields = ["name", "color", "order"]
    template_name = "finance/partials/sankey_rule_form.html"
    permission_required = "finance.change_sankeycategory"

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["color"].widget.input_type = "color"
        return _bootstrap_styled(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["scheme"] = self.request.GET.get("scheme", "")
        context["is_create"] = False
        context["is_category"] = True
        return context

    def form_valid(self, form):
        category = form.save()
        scheme = self.request.GET.get("scheme", "")
        html = render(
            self.request,
            "finance/partials/category_header.html",
            {"category": category, "scheme": scheme, "oob": True},
        )
        html["HX-Trigger"] = "closeSankeyRuleModal"
        return html


class SankeyMaticExportView(LoginRequiredMixin, View):
    """Return a SankeyMATIC-compatible text file for the requested year/type."""

    def get(self, request, *args, **kwargs) -> HttpResponse:
        year_str = request.GET.get("year", "")
        if not year_str.isdigit():
            return HttpResponse("Missing or invalid 'year'.", status=400, content_type="text/plain")
        year = int(year_str)
        budget_str = request.GET.get("budget", "false").lower()
        is_budget = budget_str in ("true", "1", "yes", "on")
        qs = Account.objects.filter(year=year, is_budget=is_budget)
        content = build_sankeymatic_export(qs, year, _scheme_for(qs), is_budget=is_budget)
        type_label = "budget" if is_budget else "comptes"
        filename = f"sankeymatic_{type_label}_{year}.txt"
        response = HttpResponse(content, content_type="text/plain; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response
