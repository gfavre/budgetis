from django.contrib import admin
from django.contrib import messages
from django.utils.translation import gettext_lazy as _

from .models import AccountImportLog
from .models import ColumnMapping
from .tasks import import_accounts_task


class ColumnMappingInline(admin.TabularInline):
    model = ColumnMapping
    extra = 0
    readonly_fields = ("field", "column_name", "derived_from_total")
    can_delete = False


@admin.action(description=_("Relaunch import"))
def relaunch_import(modeladmin, request, queryset):
    """
    Relaunches the import task for selected logs.

    Args:
        modeladmin: The ModelAdmin instance.
        request: The current request.
        queryset: Selected AccountImportLog instances.
    """
    count = 0

    for log in queryset:
        import_accounts_task.delay(log.id)
        count += 1

    messages.success(
        request,
        _("%(count)s import(s) relaunched successfully.") % {"count": count},
    )


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
    actions = [relaunch_import]


@admin.register(ColumnMapping)
class ColumnMappingAdmin(admin.ModelAdmin):
    date_hierarchy = "created_at"
    list_display = ("field", "log", "column_name", "created_at")
    list_filter = ("field", "derived_from_total")
    search_fields = ("column_name", "log__launched_by__username")
