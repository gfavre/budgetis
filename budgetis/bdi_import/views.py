from pathlib import Path
from tempfile import NamedTemporaryFile

from django.contrib import messages
from django.urls import reverse_lazy
from django.views.generic import FormView

# from django.shortcuts import redirect
from .forms import AccountImportForm
from .models import AccountImportLog


class AccountImportView(FormView):
    template_name = "bdi_import/account_import.html"
    form_class = AccountImportForm
    success_url = reverse_lazy("bdi_import:account-import")

    def form_valid(self, form):
        account_file = form.cleaned_data["account_file"]
        year = form.cleaned_data["year"]
        is_budget = form.cleaned_data["is_budget"] == "budget"
        extension = Path(account_file.name).suffix.lower()
        if extension not in [".csv", ".xlsx"]:
            form.add_error("account_file", "Unsupported file type.")
            return self.form_invalid(form)

        with NamedTemporaryFile(delete=False, suffix=extension) as tmp:
            for chunk in account_file.chunks():
                tmp.write(chunk)
            log = AccountImportLog.objects.create(
                year=year,
                is_budget=is_budget,
                launched_by=self.request.user,
                dry_run=False,
                file=account_file,
                source_year=form.cleaned_data.get("source_year"),
                copy_responsibles=form.cleaned_data.get("copy_responsibles"),
                copy_labels=form.cleaned_data.get("copy_labels"),
                copy_visibility=form.cleaned_data.get("copy_visibility"),
                copy_comments=form.cleaned_data.get("copy_comments"),
            )
            log.save()

        messages.success(self.request, "Import lancé en arrière-plan.")
        return super().form_valid(form)
