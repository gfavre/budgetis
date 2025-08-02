import logging

from celery import shared_task
from django.utils.translation import gettext as _

from .importers import import_accounts_from_dataframe
from .models import AccountImportLog
from .utils import load_account_dataframe


logger = logging.getLogger(__name__)


@shared_task
def import_accounts_task(log_id: int):
    log = AccountImportLog.objects.get(pk=log_id)

    log.status = AccountImportLog.Status.STARTED
    log.message = "Import started."
    log.save(update_fields=["status", "message"])

    try:
        account_rows = load_account_dataframe(log.file.path)
    except FileNotFoundError:
        log.status = AccountImportLog.Status.FAILED
        log.message = _("The import file could not be found.")
        log.save(update_fields=["status", "message"])
        return
    except Exception as e:
        log.status = AccountImportLog.Status.FAILED
        log.message = f"Error while loading the import file: {e}"
        log.save(update_fields=["status", "message"])
        raise
    mapping_qs = log.column_mappings.all()
    column_map = {m.field: m.column_name for m in mapping_qs}
    logger.info("Column map passed to import: %s", column_map)

    derived_from_total = any(m.field == "total" and m.derived_from_total for m in mapping_qs)

    try:
        import_accounts_from_dataframe(
            account_rows=account_rows,
            is_budget=log.is_budget,
            year=log.year,
            dry_run=log.dry_run,
            source_year=log.source_year,
            copy_responsibles=log.copy_responsibles,
            copy_labels=log.copy_labels,
            copy_visibility=log.copy_visibility,
            copy_comments=log.copy_comments,
            column_map=column_map,
            derived_from_total=derived_from_total,
        )
    except ValueError as ve:
        log.status = AccountImportLog.Status.FAILED
        log.message = _("Import failed: ") + str(ve)
        log.save(update_fields=["status", "message"])
        return
    except Exception as e:
        log.status = AccountImportLog.Status.FAILED
        log.message = _("Unexpected error: ") + str(e)
        log.save(update_fields=["status", "message"])
        logger.exception(f"[Import] Unexpected failure for {log}")
        raise

    log.status = AccountImportLog.Status.SUCCESS
    log.message = "Import completed successfully."
    log.save(update_fields=["status", "message"])
