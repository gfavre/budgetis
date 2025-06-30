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
    csv_file = forms.FileField(label=_("CSV file"), help_text=_("Upload a CSV file with account data."))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["year"].initial = date.today().year  # noqa: DTZ011
