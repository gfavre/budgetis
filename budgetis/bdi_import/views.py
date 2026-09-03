from contextlib import suppress
from pathlib import Path
from tempfile import NamedTemporaryFile

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.shortcuts import render
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import FormView
from django.views.generic import View

from budgetis.common.models import ChartScheme

from .forms import AccountImportForm
from .models import AccountImportLog
from .models import ColumnMapping
from .tasks import import_accounts_task
from .utils import find_first_significant_content_row
from .utils import load_dataframe_with_header


class AccountImportView(LoginRequiredMixin, FormView):
    template_name = "bdi_import/account_import.html"
    form_class = AccountImportForm
    success_url = reverse_lazy("bdi_import:account-import")
    import_kind = AccountImportLog.ImportKind.BDI
    default_scheme = ChartScheme.MCH1
    title = _("Import from BDI")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = self.title
        return context

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["default_scheme"] = self.default_scheme
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
                        "scheme": log.scheme,
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
        scheme = form.cleaned_data["scheme"]

        edit_id = self.request.GET.get("edit")
        if edit_id:
            log = get_object_or_404(AccountImportLog, pk=edit_id)
            log.year = year
            log.is_budget = is_budget
            log.scheme = scheme
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
                    scheme=scheme,
                    kind=self.import_kind,
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


class ExcelImportView(AccountImportView):
    """
    Same pipeline as AccountImportView, for a manually-prepared Excel budget
    sheet rather than a BDI software export - distinguished only by `kind`
    (routes the mapping step's "back"/edit links to this screen) and its
    column-mapping choices (function/nature/sub_account split across separate
    columns, a per-row responsible trigram) that a BDI export never needs.
    """

    import_kind = AccountImportLog.ImportKind.EXCEL
    default_scheme = ChartScheme.MCH2
    title = _("Import Excel")


IMPORT_ENTRY_URL_NAMES: dict[str, str] = {
    AccountImportLog.ImportKind.BDI: "bdi_import:account-import",
    AccountImportLog.ImportKind.EXCEL: "bdi_import:excel-import",
}

# Groups the mapping dropdown's options into optgroups, purely for readability
# - not a model concern, this order/grouping has no bearing on import logic.
_F = ColumnMapping.Field
FIELD_GROUPS: list[tuple[str, list[ColumnMapping.Field]]] = [
    (_("Account identity"), [_F.CODE, _F.FUNCTION, _F.NATURE, _F.SUB_ACCOUNT]),
    (_("Account label"), [_F.LABEL]),
    (_("Responsible"), [_F.RESPONSIBLE]),
    (_("Amounts"), [_F.CHARGES, _F.REVENUES, _F.TOTAL]),
]


def _column_has_data(series) -> bool:
    """A column is worth showing in the mapping UI only if it has any real value anywhere in the file."""
    return bool(series.dropna().astype(str).str.strip().ne("").any())


class AccountMappingView(LoginRequiredMixin, View):
    template_name = "bdi_import/account_mapping.html"

    def get(self, request, log_id):
        log = get_object_or_404(AccountImportLog, pk=log_id)
        path = log.file.path
        entry_url_name = IMPORT_ENTRY_URL_NAMES[log.kind]

        try:
            uploaded_df = load_dataframe_with_header(path)
            data_start_idx = find_first_significant_content_row(uploaded_df)
            preview_rows = uploaded_df.iloc[data_start_idx : data_start_idx + 10]
            columns = [col for col in uploaded_df.columns if _column_has_data(uploaded_df[col])]
            column_samples = {
                col: [v for v in preview_rows[col].dropna().astype(str).tolist() if v][:3] for col in columns
            }
            field_groups = [
                (group_label, [(field.value, field.label) for field in fields]) for group_label, fields in FIELD_GROUPS
            ]

            context = {
                "log": log,
                "columns": columns,
                "column_samples": column_samples,
                "preview_rows": preview_rows.fillna("").to_dict(orient="records"),
                "field_groups": field_groups,
                "import_entry_url_name": entry_url_name,
            }
            return render(request, self.template_name, context)

        except ValueError as exc:
            messages.error(request, _("Could not process the uploaded file: %(error)s") % {"error": str(exc)})
            return redirect(entry_url_name)

    def post(self, request, log_id):
        log = get_object_or_404(AccountImportLog, pk=log_id)
        log.column_mappings.all().delete()

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
                    # "Total (signed)" implies sign-derived charges/revenues by
                    # definition - there is no other way to interpret that field.
                    derived_from_total=(field == ColumnMapping.Field.TOTAL),
                )
        import_accounts_task.delay(log.id)

        messages.success(request, _("Column mapping saved. Import will now be launched."))
        return redirect(IMPORT_ENTRY_URL_NAMES[log.kind])
