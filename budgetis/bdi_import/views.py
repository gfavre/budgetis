from tempfile import NamedTemporaryFile

from django.contrib import messages
from django.urls import reverse_lazy
from django.views.generic import FormView

from .forms import AccountImportForm
from .models import AccountImportLog
from .tasks import import_accounts_task


class AccountImportView(FormView):
    template_name = "bdi_import/account_import.html"
    form_class = AccountImportForm
    success_url = reverse_lazy("bdi_import:account-import")

    def form_valid(self, form):
        csv_file = form.cleaned_data["csv_file"]
        year = form.cleaned_data["year"]
        is_budget = form.cleaned_data["is_budget"] == "budget"

        with NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
            for chunk in csv_file.chunks():
                tmp.write(chunk)
            tmp_path = tmp.name
            log = AccountImportLog.objects.create(
                year=year,
                is_budget=is_budget,
                csv_path=tmp_path,
                launched_by=self.request.user,
                dry_run=False,
                status="pending",
            )
        import_accounts_task.delay(
            csv_path=tmp_path,
            year=year,
            is_budget=is_budget,
            dry_run=False,
            log_id=log.id,
        )

        messages.success(self.request, "Import lancé en arrière-plan.")
        return super().form_valid(form)
