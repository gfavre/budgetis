from celery import shared_task

from .importers import import_accounts_from_dataframe
from .models import AccountImportLog
from .utils import load_account_dataframe


@shared_task
def import_accounts_task(
    file_path: str, year: int, *, is_budget: bool = False, dry_run: bool = False, log_id: int | None = None
) -> None:
    log = None
    if log_id:
        log = AccountImportLog.objects.filter(pk=log_id).first()
        if log:
            log.status = "started"
            log.save()

    try:
        account_rows = load_account_dataframe(file_path)
        import_accounts_from_dataframe(account_rows=account_rows, is_budget=is_budget, year=year, dry_run=dry_run)

        if log:
            log.status = "success"
            log.message = "Import completed successfully."
            log.save()
    except Exception as e:
        if log:
            log.status = "failed"
            log.message = str(e)
            log.save()
        raise
