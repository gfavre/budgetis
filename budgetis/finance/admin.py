from django.contrib import admin

from .models import AvailableYear
from .models import SankeyAccountCodeRule
from .models import SankeyCategory
from .models import SankeyLabelRule
from .models import SankeyNatureRangeRule


@admin.register(AvailableYear)
class AvailableYearAdmin(admin.ModelAdmin):
    list_display = ("year", "type", "created_at")
    list_filter = ("type",)
    ordering = ("-year",)
    list_display_links = ("year",)


@admin.register(SankeyCategory)
class SankeyCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "flow", "color", "order")
    list_filter = ("flow",)
    ordering = ("flow", "order")


@admin.register(SankeyNatureRangeRule)
class SankeyNatureRangeRuleAdmin(admin.ModelAdmin):
    list_display = ("scheme", "nature_start", "nature_end", "priority", "category")
    list_filter = ("scheme", "category")
    ordering = ("scheme", "priority", "nature_start")


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
