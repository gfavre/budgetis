from datetime import date

from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML
from crispy_forms.layout import Fieldset
from crispy_forms.layout import Layout
from crispy_forms.layout import Submit
from django import forms
from django.utils.translation import gettext_lazy as _

from budgetis.finance.models import AvailableYear


class AccountImportForm(forms.Form):
    year = forms.IntegerField(label=_("Year"), min_value=2000, max_value=2100)
    is_budget = forms.ChoiceField(
        label=_("Nature"),
        choices=[("budget", "Budget"), ("actual", "Comptes")],
        widget=forms.RadioSelect,
    )
    source_year = forms.ModelChoiceField(
        label=_("Copy settings from"),
        required=False,
        queryset=AvailableYear.objects.none(),  # défini dynamiquement dans __init__
        help_text=_("Select the year from which to copy settings (if any)."),
    )
    copy_responsibles = forms.BooleanField(label=_("Copy responsibles"), required=False, initial=True)
    copy_labels = forms.BooleanField(label=_("Copy account labels"), required=False, initial=True)
    copy_visibility = forms.BooleanField(label=_("Copy visibility"), required=False, initial=True)
    copy_comments = forms.BooleanField(label=_("Copy comments"), required=False, initial=True)

    account_file = forms.FileField(
        label=_("Accounts list file"), help_text=_("Upload a CSV or XSLX file with account data.")
    )

    def __init__(self, *args, edit_log=None, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["year"].initial = date.today().year  # noqa: DTZ011

        self.helper = FormHelper()
        self.helper.form_method = "post"
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Fieldset(
                _("Import target"),
                "year",
                "is_budget",
            ),
            Fieldset(
                _("Copy settings from another year"),
                "source_year",
                "copy_responsibles",
                "copy_labels",
                "copy_visibility",
                "copy_comments",
            ),
            Fieldset(
                _("Account file"),
                "account_file",
            ),
            HTML("<hr>"),
            Submit("submit", _("Import"), css_class="btn btn-primary"),
        )

        if edit_log:
            self.fields["account_file"].required = False
            self.fields["account_file"].widget = forms.HiddenInput()
            self.fields["account_file"].label = _("File already uploaded")

            for fieldset in self.helper.layout:
                if isinstance(fieldset, Fieldset) and "account_file" in fieldset.fields:
                    # Remplacer le champ "account_file" par un bloc HTML affichant le fichier
                    fieldset.fields = [
                        HTML(
                            f"""
                                <div class="mb-3">
                                  <label class="form-label fw-bold">{_("Uploaded file")}</label>
                                  <div class="form-control bg-light">
                                    <i class="bi bi-file-earmark-text me-2"></i>
                                    {edit_log.file.name.split("/")[-1]} ({edit_log.file.size / 1024:.1f} KB)
                                  </div>
                                </div>
                                """
                        )
                    ]
        self.fields["source_year"].queryset = AvailableYear.objects.order_by("-year")

    def clean_file(self):
        uploaded_file = self.cleaned_data["account_file"]
        valid_extensions = [".csv", ".xlsx"]
        if not any(uploaded_file.name.lower().endswith(ext) for ext in valid_extensions):
            raise forms.ValidationError(_("Please upload a CSV or XLSX file."))
        return uploaded_file
