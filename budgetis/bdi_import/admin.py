from django.contrib import admin

from .models import AccountImportLog
from .models import ColumnMapping


class ColumnMappingInline(admin.TabularInline):
    model = ColumnMapping
    extra = 0
    readonly_fields = ("field", "column_name", "derived_from_total")
    can_delete = False


@admin.register(AccountImportLog)
class AccountImportLogAdmin(admin.ModelAdmin):
    date_hierarchy = "created_at"
    list_display = (
        "created_at",
        "year",
        "is_budget",
        "launched_by",
        "dry_run",
        "status",
    )
    list_filter = ("is_budget", "dry_run", "status", "year")
    search_fields = ("file", "message", "launched_by__username")
    readonly_fields = ("created_at", "status", "message")
    inlines = [ColumnMappingInline]


@admin.register(ColumnMapping)
class ColumnMappingAdmin(admin.ModelAdmin):
    date_hierarchy = "created_at"
    list_display = ("field", "log", "column_name", "created_at")
    list_filter = ("field", "derived_from_total")
    search_fields = ("column_name", "log__launched_by__username")
