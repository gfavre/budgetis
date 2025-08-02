from contextlib import suppress
from pathlib import Path
from tempfile import NamedTemporaryFile

import pandas as pd
from django.contrib import messages
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.shortcuts import render
from django.urls import reverse_lazy
from django.utils.translation import gettext as _
from django.views.generic import FormView
from django.views.generic import View

from .forms import AccountImportForm
from .models import AccountImportLog
from .models import ColumnMapping
from .tasks import import_accounts_task
from .utils import detect_first_data_row


class AccountImportView(FormView):
    template_name = "bdi_import/account_import.html"
    form_class = AccountImportForm
    success_url = reverse_lazy("bdi_import:account-import")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        edit_id = self.request.GET.get("edit")
        if edit_id:
            with suppress(AccountImportLog.DoesNotExist):
                kwargs["edit_log"] = AccountImportLog.objects.get(pk=edit_id)
        return kwargs

    def get_initial(self):
        initial = super().get_initial()
        edit_id = self.request.GET.get("edit")
        if edit_id:
            try:
                log = AccountImportLog.objects.get(pk=edit_id)
                initial.update(
                    {
                        "year": log.year,
                        "is_budget": "budget" if log.is_budget else "actual",
                        "source_year": log.source_year,
                        "copy_responsibles": log.copy_responsibles,
                        "copy_labels": log.copy_labels,
                        "copy_visibility": log.copy_visibility,
                        "copy_comments": log.copy_comments,
                    }
                )
            except AccountImportLog.DoesNotExist:
                pass
        return initial

    def form_valid(self, form):
        account_file = form.cleaned_data["account_file"]
        year = form.cleaned_data["year"]
        is_budget = form.cleaned_data["is_budget"] == "budget"

        edit_id = self.request.GET.get("edit")
        if edit_id:
            log = get_object_or_404(AccountImportLog, pk=edit_id)
            log.year = year
            log.is_budget = is_budget
            log.source_year = form.cleaned_data.get("source_year")
            log.copy_responsibles = form.cleaned_data.get("copy_responsibles")
            log.copy_labels = form.cleaned_data.get("copy_labels")
            log.copy_visibility = form.cleaned_data.get("copy_visibility")
            log.copy_comments = form.cleaned_data.get("copy_comments")
            log.save()
        else:
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
        return redirect("bdi_import:account-mapping", log_id=log.id)


class AccountMappingView(View):
    template_name = "bdi_import/account_mapping.html"

    def get(self, request, log_id):
        log = get_object_or_404(AccountImportLog, pk=log_id)
        path = log.file.path
        is_xlsx = path.endswith(".xlsx")

        # 1. Charger sans header pour détecter la vraie ligne d'entête
        raw_df = pd.read_excel(path, sheet_name=0, header=None) if is_xlsx else pd.read_csv(path, header=None)
        header_row = detect_first_data_row(raw_df)

        # 2. Recharger avec le header détecté
        headed_df = (
            pd.read_excel(path, sheet_name=0, header=header_row) if is_xlsx else pd.read_csv(path, header=header_row)
        )

        # 3. Détecter première ligne significative (≥ 3 valeurs non vides / non nulles / ≠ "0")
        def is_significant(val: str) -> bool:
            return val.strip().lower() not in {"", "0", "0.0", "nan"}

        def find_first_significant_content_row(df: pd.DataFrame, min_valid_fields: int = 5) -> int:
            for idx, row in df.iterrows():
                str_values = row.dropna().astype(str)
                if sum(is_significant(v) for v in str_values) >= min_valid_fields:
                    return idx
            msg = "No sufficiently filled data row found."
            raise ValueError(msg)

        data_start_idx = find_first_significant_content_row(headed_df)

        preview_rows = headed_df.iloc[data_start_idx : data_start_idx + 10]

        context = {
            "log": log,
            "columns": list(headed_df.columns),
            "preview_rows": preview_rows.to_dict(orient="records"),
            "field_choices": ColumnMapping.Field.choices,
        }
        return render(request, self.template_name, context)

    def post(self, request, log_id):
        log = get_object_or_404(AccountImportLog, pk=log_id)
        log.column_mappings.all().delete()

        derived_from_total = request.POST.get("derived_from_total") == "on"
        column_map = {}
        for key in request.POST:
            if key.startswith("column_map[") and key.endswith("]"):
                column_name = key[len("column_map[") : -1]
                field_value = request.POST[key]
                if field_value:
                    column_map[column_name] = field_value

        for column_name, field in column_map.items():
            if field:
                ColumnMapping.objects.create(
                    log=log,
                    field=field,
                    column_name=column_name,
                    derived_from_total=(field == ColumnMapping.Field.TOTAL and derived_from_total),
                )
        import_accounts_task.delay(log.id)

        messages.success(request, _("Column mapping saved. Import will now be launched."))
        return redirect("bdi_import:account-import")
