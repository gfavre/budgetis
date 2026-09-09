from functools import partial

from django.contrib import admin
from django.contrib import messages
from django.db import transaction
from django.utils.translation import gettext_lazy as _

from .models import AccountImportLog
from .models import ColumnMapping
from .tasks import import_accounts_task


class ColumnMappingInline(admin.TabularInline):
    model = ColumnMapping
    extra = 0
    readonly_fields = ("field", "column_name", "derived_from_total")
    can_delete = False


@admin.action(description=_("Relaunch failed imports"), permissions=["change"])
def relaunch_import(modeladmin, request, queryset):
    """
    Relaunches the import task for selected logs.

    Args:
        modeladmin: The ModelAdmin instance.
        request: The current request.
        queryset: Selected AccountImportLog instances.
    """
    count = 0

    with transaction.atomic():
        for log in queryset.select_for_update().filter(status=AccountImportLog.Status.FAILED):
            log.status = AccountImportLog.Status.PENDING
            log.save(update_fields=["status", "updated_at"])
            transaction.on_commit(partial(_enqueue_retry, log.pk))
            count += 1

    modeladmin.message_user(
        request,
        _("%(count)s failed import(s) queued for retry. Other selected imports were skipped.") % {"count": count},
        level=messages.SUCCESS if count else messages.WARNING,
    )


def _enqueue_retry(log_id):
    try:
        import_accounts_task.delay(log_id)
    except Exception:
        AccountImportLog.objects.filter(pk=log_id, status=AccountImportLog.Status.PENDING).update(
            status=AccountImportLog.Status.FAILED
        )
        raise


@admin.register(AccountImportLog)
class AccountImportLogAdmin(admin.ModelAdmin):
    date_hierarchy = "created_at"
    list_display = (
        "created_at",
        "year",
        "is_budget",
        "scheme",
        "kind",
        "launched_by",
        "dry_run",
        "status",
    )
    list_filter = ("kind", "scheme", "is_budget", "dry_run", "status", "year")
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
