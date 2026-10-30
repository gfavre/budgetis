from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from .models import SankeyAccountCodeRule
from .models import SankeyCategory


EXACT_CODE_FIELDS = ("function", "nature", "sub_account")
DUPLICATE_EXACT_CODE_ERROR = "duplicate_exact_code"
DUPLICATE_CATEGORY_ERROR = "duplicate_category"


class SankeyCategoryForm(forms.ModelForm):
    conflicting_category = None

    class Meta:
        model = SankeyCategory
        fields = ("name", "flow", "color", "order")

    def find_conflicting_category(self):
        if "name" not in self.cleaned_data:
            return None
        return SankeyCategory.objects.filter(name=self.cleaned_data["name"]).exclude(pk=self.instance.pk).first()

    def add_duplicate_error(self) -> bool:
        category = self.find_conflicting_category()
        if category is None:
            return False
        self.conflicting_category = category
        self.add_error(
            "name",
            ValidationError(
                _("Category %(name)s already exists in %(group)s. Categories are shared by MCH1 and MCH2."),
                code=DUPLICATE_CATEGORY_ERROR,
                params={"name": category.name, "group": category.get_flow_display()},
            ),
        )
        return True

    def validate_unique(self):
        # Name is the category's only unique editable field. Report its actual
        # location instead of Django's generic model/field uniqueness message.
        self.add_duplicate_error()


class SankeyCategoryEditForm(SankeyCategoryForm):
    class Meta(SankeyCategoryForm.Meta):
        fields = ("name", "color", "order")


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
