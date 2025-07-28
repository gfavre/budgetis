from decimal import Decimal
from typing import Any

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView

from .forms import AccountFilterForm
from .models import Account
from .models import GroupResponsibility


class AccountExplorerView(LoginRequiredMixin, TemplateView):
    template_name = "accounting/account_explorer.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        form = AccountFilterForm(self.request.GET or None)

        context["form"] = form
        context["accounts_by_group"] = {}
        grouped = {}

        if form.is_valid():
            year = int(form.cleaned_data["year"])
            only_resp = form.cleaned_data["only_responsible"]

            qs = Account.objects.filter(
                year=year,
                is_budget=False,
                group__isnull=False,
            ).select_related("group__supergroup__metagroup")

            if only_resp:
                groups = GroupResponsibility.objects.filter(year=year, responsible=self.request.user).values_list(
                    "group_id", flat=True
                )
                qs = qs.filter(group__in=groups)

            for account in qs:
                mg = account.group.supergroup.metagroup
                sg = account.group.supergroup
                ag = account.group

                grouped.setdefault(mg, {}).setdefault(sg, {}).setdefault(
                    ag, {"accounts": [], "total_charges": Decimal(0), "total_revenues": Decimal(0)}
                )

                ag_data = grouped[mg][sg][ag]
                ag_data["accounts"].append(account)
                ag_data["total_charges"] += account.charges
                ag_data["total_revenues"] += account.revenues

        context["accounts_by_group"] = grouped
        return context
