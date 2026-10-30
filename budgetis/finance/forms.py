from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from .models import SankeyAccountCodeRule


EXACT_CODE_FIELDS = ("function", "nature", "sub_account")
DUPLICATE_EXACT_CODE_ERROR = "duplicate_exact_code"


class SankeyAccountCodeRuleForm(forms.ModelForm):
    conflicting_rule = None

    class Meta:
        model = SankeyAccountCodeRule
        fields = EXACT_CODE_FIELDS

    def find_conflicting_rule(self):
        if any(field not in self.cleaned_data for field in EXACT_CODE_FIELDS):
            return None
        return (
            SankeyAccountCodeRule.objects.filter(
                scheme=self.instance.scheme,
                **{field: self.cleaned_data[field] for field in EXACT_CODE_FIELDS},
            )
            .exclude(pk=self.instance.pk)
            .select_related("category")
            .first()
        )

    def add_duplicate_error(self) -> bool:
        rule = self.find_conflicting_rule()
        if rule is None:
            return False
        self.conflicting_rule = rule
        code = f"{rule.function}.{rule.nature}"
        if rule.sub_account:
            code += f".{rule.sub_account}"
        self.add_error(
            None,
            ValidationError(
                _("Exact code %(code)s already exists in %(category)s (%(scheme)s)."),
                code=DUPLICATE_EXACT_CODE_ERROR,
                params={"code": code, "category": rule.category.name, "scheme": rule.scheme.upper()},
            ),
        )
        return True

    def clean(self):
        cleaned_data = super().clean()
        # Scheme comes from the URL/instance, so ModelForm's automatic
        # uniqueness validation excludes it along with this compound key.
        self.add_duplicate_error()
        return cleaned_data
