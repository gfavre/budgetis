from __future__ import annotations

from typing import Any

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.http import JsonResponse
from django.views import View
from django.views.generic import TemplateView

from budgetis.accounting.models import Account
from budgetis.common.models import ChartScheme

from .builders import build_income_budget_canton_intercos_commune
from .builders import build_sankeymatic_export
from .models import AvailableYear


def _scheme_for(qs) -> str:
    """Accounts for a given (year, is_budget) are homogeneous in scheme; default to MCH1 if empty."""
    first = qs.values_list("scheme", flat=True).first()
    return first or ChartScheme.MCH1


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
        available = list(AvailableYear.objects.order_by("-year").values_list("year", flat=True).distinct())
        actual_years = list(
            AvailableYear.objects.filter(type=AvailableYear.YearType.ACTUAL)
            .order_by("-year")
            .values_list("year", flat=True)
        )
        default_year = actual_years[0] if actual_years else (available[0] if available else None)
        context["available_years"] = available
        context["default_year"] = default_year
        return context


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
