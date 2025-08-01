from celery import shared_task

from .importers import import_accounts_from_dataframe
from .models import AccountImportLog
from .utils import load_account_dataframe


@shared_task
def import_accounts_task(log_id: int):
    log = AccountImportLog.objects.get(pk=log_id)

    log.status = AccountImportLog.Status.STARTED
    log.message = "Import started."
    log.save(update_fields=["status", "message"])

    try:
        account_rows = load_account_dataframe(log.file.path)
    except Exception as e:
        log.status = AccountImportLog.Status.FAILED
        log.message = f"Error while loading the import file: {e}"
        log.save(update_fields=["status", "message"])
        raise

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
        )
    except Exception as e:
        log.status = AccountImportLog.Status.FAILED
        log.message = f"Error during import execution: {e}"
        log.save(update_fields=["status", "message"])
        raise

    log.status = AccountImportLog.Status.SUCCESS
    log.message = "Import completed successfully."
    log.save(update_fields=["status", "message"])
