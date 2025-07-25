from datetime import date

from django import forms
from django.utils.translation import gettext_lazy as _


class AccountImportForm(forms.Form):
    year = forms.IntegerField(label=_("Year"), min_value=2000, max_value=2100)
    is_budget = forms.ChoiceField(
        label=_("Nature"),
        choices=[("budget", "Budget"), ("actual", "Comptes")],
        widget=forms.RadioSelect,
    )
    account_file = forms.FileField(
        label=_("Accounts list file"), help_text=_("Upload a CSV or XSLX file with account data.")
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["year"].initial = date.today().year  # noqa: DTZ011

    def clean_file(self):
        uploaded_file = self.cleaned_data["account_file"]
        valid_extensions = [".csv", ".xlsx"]
        if not any(uploaded_file.name.lower().endswith(ext) for ext in valid_extensions):
            raise forms.ValidationError(_("Please upload a CSV or XLSX file."))
        return uploaded_file
