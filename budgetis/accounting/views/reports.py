from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView

from budgetis.accounting.migration_report import build_migration_report


class MigrationReportView(LoginRequiredMixin, TemplateView):
    template_name = "accounting/reports/migration.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["report"] = build_migration_report()
        return context
