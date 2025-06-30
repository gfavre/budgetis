from django.contrib import admin

from .models import AccountImportLog


@admin.register(AccountImportLog)
class AccountImportLogAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "year",
        "is_budget",
        "launched_by",
        "dry_run",
        "status",
    )
    list_filter = ("is_budget", "dry_run", "status", "year")
    search_fields = ("csv_path", "message", "launched_by__username")
    readonly_fields = ("created_at", "status", "message")
    date_hierarchy = "created_at"
