from django import forms
from django.contrib.admin import widgets as admin_widgets
from django.contrib.auth import get_user_model
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from budgetis.finance.models import AvailableYear

from .models import Account
from .models import AccountComment
from .models import AccountGroup


class AccountGroupForm(forms.ModelForm):
    accounts = forms.ModelMultipleChoiceField(
        queryset=Account.objects.order_by("function", "nature", "sub_account"),
        required=False,
        widget=admin_widgets.FilteredSelectMultiple("Accounts", is_stacked=False),
    )

    class Meta:
        model = AccountGroup
        fields = ("id", "code", "label", "scheme", "level", "parent", "accounts")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["accounts"].initial = self.instance.accounts.all()
            self.fields["parent"].queryset = AccountGroup.objects.exclude(pk=self.instance.pk).order_by(
                "scheme", "level", "code"
            )


class AccountFilterForm(forms.Form):
    year = forms.ChoiceField(label=_("Year"))
    only_responsible = forms.BooleanField(
        label=_("Show only my accounts"),
        required=False,
        initial=True,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["year"].choices = [("", _("- Select year -"))] + [
            (str(y), str(y)) for y in AvailableYear.objects.values_list("year", flat=True).distinct().order_by("-year")
        ]


class NatureFilterForm(AccountFilterForm):
    detail = forms.BooleanField(
        required=False,
        initial=False,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["detail"].label = format_html(
            '<i class="bi bi-eye"></i> {}', _("Show sub-accounts (detail down to 3-digit nature codes)")
        )


class ReassignResponsibleFormBase(forms.Form):
    responsible = forms.ModelChoiceField(
        label=_("Responsible"),
        queryset=get_user_model().objects.order_by("name"),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["responsible"].label_from_instance = str


class ReassignAccountResponsibleForm(ReassignResponsibleFormBase):
    """Reassigns the AccountGroup responsible for the year of each selected account."""


class ReassignGroupResponsibleForm(ReassignResponsibleFormBase):
    """Reassigns the AccountGroup responsible for an explicitly chosen year."""

    year = forms.ChoiceField(label=_("Year"))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["year"].choices = [
            (str(y), str(y)) for y in AvailableYear.objects.values_list("year", flat=True).distinct().order_by("-year")
        ]


class AccountAmountForm(forms.Form):
    """Edits a single charges/revenues Decimal field, named dynamically by `kind` in the view."""

    amount = forms.DecimalField(
        label=_("Amount"),
        max_digits=15,
        decimal_places=2,
        # localize=False: an <input type="number"> requires a period decimal
        # separator - Django's fr-CH locale otherwise renders (and expects)
        # a comma, which the input then silently rejects and shows empty.
        localize=False,
        widget=forms.NumberInput(attrs={"step": "0.01", "class": "form-control text-end"}),
    )


class AccountCommentForm(forms.ModelForm):
    class Meta:
        model = AccountComment
        fields = ["content"]
        widgets = {
            "content": forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
        }
