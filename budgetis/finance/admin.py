from django import forms
from django.contrib import admin
from django.utils.safestring import mark_safe

from .models import AvailableYear
from .models import SankeyAccountCodeRule
from .models import SankeyCategory
from .models import SankeyFunctionNatureRule
from .models import SankeyLabelRule
from .models import SankeyNatureRangeRule


@admin.register(AvailableYear)
class AvailableYearAdmin(admin.ModelAdmin):
    list_display = ("year", "type", "created_at")
    list_filter = ("type",)
    ordering = ("-year",)
    list_display_links = ("year",)


class SankeyCategoryForm(forms.ModelForm):
    class Meta:
        model = SankeyCategory
        fields = "__all__"  # noqa: DJ007
        widgets = {
            "color": forms.TextInput(attrs={"type": "color"}),
        }


@admin.register(SankeyCategory)
class SankeyCategoryAdmin(admin.ModelAdmin):
    form = SankeyCategoryForm
    list_display = ("name", "flow", "color_swatch", "order")
    list_filter = ("flow",)
    ordering = ("flow", "order")

    @admin.display(description="Couleur")
    def color_swatch(self, obj: SankeyCategory) -> str:
        return mark_safe(  # noqa: S308
            f'<span style="display:inline-block;width:1em;height:1em;'
            f'background:{obj.color};border:1px solid rgba(0,0,0,0.25);vertical-align:middle;"></span> '
            f"{obj.color}"
        )


@admin.register(SankeyNatureRangeRule)
class SankeyNatureRangeRuleAdmin(admin.ModelAdmin):
    list_display = ("scheme", "nature_start", "nature_end", "priority", "category")
    list_filter = ("scheme", "category")
    ordering = ("scheme", "priority", "nature_start")


@admin.register(SankeyFunctionNatureRule)
class SankeyFunctionNatureRuleAdmin(admin.ModelAdmin):
    list_display = ("scheme", "function_prefix", "nature_start", "nature_end", "category")
    list_filter = ("scheme", "category")
    search_fields = ("function_prefix",)
    ordering = ("scheme", "function_prefix", "nature_start")


@admin.register(SankeyAccountCodeRule)
class SankeyAccountCodeRuleAdmin(admin.ModelAdmin):
    list_display = ("scheme", "function", "nature", "sub_account", "category")
    list_filter = ("scheme", "category")
    search_fields = ("function", "nature", "sub_account")
    ordering = ("scheme", "function", "nature")


@admin.register(SankeyLabelRule)
class SankeyLabelRuleAdmin(admin.ModelAdmin):
    list_display = ("scheme", "pattern", "category")
    list_filter = ("scheme", "category")
    search_fields = ("pattern",)
    ordering = ("scheme", "pattern")
