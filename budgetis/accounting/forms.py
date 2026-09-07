from typing import Any

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


def _year_choices() -> list[tuple[str, Any]]:
    return [("", _("- Select year -"))] + [
        (str(y), str(y)) for y in AvailableYear.objects.values_list("year", flat=True).distinct().order_by("-year")
    ]


class YearFilterForm(forms.Form):
    """
    Just the year picker - for pages that report on the whole commune at
    once (e.g. the staged result) rather than listing individual accounts,
    where "only my accounts" has no meaning to filter by.
    """

    year = forms.ChoiceField(label=_("Year"))

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["year"].choices = _year_choices()


class AccountFilterForm(forms.Form):
    """
    `user`, when passed, drops the "only my accounts" checkbox entirely for a
    non-municipal user - GroupResponsibility assignments are a municipal
    officer's own accounts, a concept that doesn't apply to Bourse staff, who
    handle every account.
    """

    year = forms.ChoiceField(label=_("Year"))
    only_responsible = forms.BooleanField(
        label=_("Show only my accounts"),
        required=False,
        initial=True,
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["year"].choices = _year_choices()
        if user is not None and not user.is_municipal:
            del self.fields["only_responsible"]


class NatureFilterForm(YearFilterForm):
    """
    The by-nature reports group every account by its nature code, regardless
    of who's responsible for it - like the staged result, "only my accounts"
    has no meaning here, so this builds on YearFilterForm, not
    AccountFilterForm.
    """

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
    """
    Reassigns the responsible for the year of each selected account - either
    for the whole AccountGroup those accounts belong to, or just for their
    own 5-digit function(s) (see GroupResponsibility's function-level
    override, used when a single group covers several sites/buildings each
    needing a different responsible).
    """

    SCOPE_GROUP = "group"
    SCOPE_FUNCTION = "function"

    scope = forms.ChoiceField(
        label=_("Scope"),
        choices=[
            (SCOPE_GROUP, _("The whole group (every function under it)")),
            (SCOPE_FUNCTION, _("Only the selected accounts' own function(s)")),
        ],
        initial=SCOPE_GROUP,
        widget=forms.RadioSelect,
    )


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
