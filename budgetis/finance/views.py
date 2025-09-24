from __future__ import annotations

from typing import Any

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views import View
from django.views.generic import TemplateView

from budgetis.accounting.models import Account

from .builders import build_income_budget_canton_intercos_commune


class SankeyDataView(LoginRequiredMixin, View):
    """
    Return Sankey data (nodes/links) as JSON for the requested parameters.

    Query params:
        year: int (required)
        is_budget: "1" or "0" (default "0")
        group_by: "group" | "function_nature" (default "group")
        value_mode: "net" | "charges" | "revenues" (default "net")
        min_amount: decimal string (default "0")
    """

    def get(self, request, *args, **kwargs) -> JsonResponse:
        year_str = request.GET.get("year", "")
        if not year_str.isdigit():
            return JsonResponse({"error": "Missing or invalid 'year'."}, status=400)

        year = int(year_str)
        qs = Account.objects.filter(year=year, is_budget=False)
        data: dict[str, Any] = build_income_budget_canton_intercos_commune(qs)
        return JsonResponse(data, safe=False)


class SankeyView(TemplateView):
    template_name = "finance/sankey.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from django.utils.timezone import now

        context["default_year"] = now().year
        return context


class SankeySimpleValuesView(LoginRequiredMixin, View):
    """
    Return the five bucket values in a fixed order for the Sankey.
    Order (top→bottom):
        - Impôts
        - Impôts aléatoires
        - Locations
        - Taxes
        - Autre revenus
    """

    def get(self, request, *args, **kwargs) -> JsonResponse:
        data: dict[str, Any] = {
            "order": [
                "Impôts",
                "Impôts aléatoires",
                "Locations",
                "Taxes",
                "Autre revenus",
            ],
            "values": [12000000, 1000000, 1500000, 500000, 2000000],
            "target": "Budget",
        }
        return JsonResponse(data)
