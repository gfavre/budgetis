from crispy_forms.helper import FormHelper
from crispy_forms.layout import Fieldset
from crispy_forms.layout import Layout
from django import forms
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.forms import inlineformset_factory
from django.forms.models import BaseInlineFormSet
from django.utils.translation import gettext_lazy as _

from budgetis.accounting.models import MCH2_FUNCTION_CODE_LENGTH
from budgetis.accounting.models import MCH2_GROUP_CODE_LENGTH
from budgetis.accounting.models import Account
from budgetis.accounting.models import AccountGroup
from budgetis.accounting.models import FunctionCategory
from budgetis.accounting.models import FunctionSplit
from budgetis.accounting.models import GroupResponsibility
from budgetis.common.models import ChartScheme
from budgetis.finance.models import AvailableYear


MCH1_LEAF_LEVEL = 3
FUNCTION_CATEGORY_PREFIX = "categories"
FUNCTION_CATEGORY_ID_FIELD = "id"


def responsible_groups():
    return AccountGroup.objects.filter(
        Q(scheme=ChartScheme.MCH1, level=MCH1_LEAF_LEVEL) | Q(scheme=ChartScheme.MCH2, level=MCH2_GROUP_CODE_LENGTH)
    )


class ResponsibilitySettingsForm(forms.ModelForm):
    year = forms.TypedChoiceField(label=_("Year"), coerce=int)
    responsible = forms.ModelChoiceField(
        label=_("Responsible"), queryset=get_user_model().objects.none(), required=False
    )

    class Meta:
        model = GroupResponsibility
        fields = ("group", "year", "function", "responsible")
        labels = {"group": _("Group")}
        help_texts = {
            "function": _("Leave blank for the whole group, or enter an existing five-digit MCH2 function."),
            "responsible": _("Function assignments take precedence over the group responsible."),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["group"].queryset = responsible_groups()
        years = set(AvailableYear.objects.values_list("year", flat=True))
        years.update(Account.objects.values_list("year", flat=True).distinct())
        years.update(GroupResponsibility.objects.values_list("year", flat=True).distinct())
        self.fields["year"].choices = [(year, year) for year in sorted(years, reverse=True)]
        self.fields["responsible"].queryset = (
            get_user_model()
            .objects.filter(Q(is_active=True) | Q(pk=self.instance.responsible_id))
            .order_by("trigram", "name")
        )
        self.fields["responsible"].label_from_instance = str
        if self.instance.pk:
            for field in ("group", "year", "function"):
                self.fields[field].disabled = True
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(Fieldset(_("Responsibility assignment"), *self.Meta.fields))

    def clean(self):
        cleaned = super().clean()
        group = cleaned.get("group")
        function = cleaned.get("function")
        year = cleaned.get("year")
        if function and group and year and not self.instance.pk:
            if (
                group.scheme != ChartScheme.MCH2
                or len(function) != MCH2_FUNCTION_CODE_LENGTH
                or not function.isascii()
                or not function.isdigit()
                or not Account.objects.filter(group=group, function=function, year=year).exists()
            ):
                self.add_error("function", _("Choose an existing MCH2 function in this group and year."))
        return cleaned


class FunctionSplitSettingsForm(forms.ModelForm):
    class Meta:
        model = FunctionSplit
        fields = ("enabled",)
        help_texts = {
            "enabled": _(
                "Enable separate Budget and Actuals tables for each function. Labels alone do not enable the split."
            )
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(Fieldset(_("Group presentation"), "enabled"))


class FunctionCategorySettingsForm(forms.ModelForm):
    class Meta:
        model = FunctionCategory
        fields = ("function", "label")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["function"].disabled = True


class BaseFunctionCategoryFormSet(BaseInlineFormSet):
    def add_fields(self, form, index):
        super().add_fields(form, index)
        form.fields[FUNCTION_CATEGORY_ID_FIELD].queryset = self.get_queryset()

    def clean(self):
        super().clean()
        for form in self.forms:
            if not form.cleaned_data or form.cleaned_data.get("DELETE"):
                continue
            function = form.cleaned_data.get("function", "")
            if function and (
                len(function) != MCH2_FUNCTION_CODE_LENGTH
                or not function.isascii()
                or not function.isdigit()
                or not function.startswith(self.instance.group.code)
            ):
                form.add_error("function", _("Function must be a five-digit code belonging to the split group."))


FunctionCategoryFormSet = inlineformset_factory(
    FunctionSplit,
    FunctionCategory,
    form=FunctionCategorySettingsForm,
    formset=BaseFunctionCategoryFormSet,
    extra=1,
    can_delete=True,
)
