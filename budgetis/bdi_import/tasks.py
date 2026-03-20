import logging

from celery import shared_task
from django.utils.translation import gettext as _

from budgetis.finance.models import AvailableYear

from .importers import import_accounts_from_dataframe
from .models import AccountImportLog
from .utils import load_account_dataframe


logger = logging.getLogger(__name__)


@shared_task(bind=True)
def import_accounts_task(self, log_id: int):  # noqa: PLR0915
    logger.info("[Import] Task received for log_id=%s", log_id)
    try:
        log = AccountImportLog.objects.get(pk=log_id)
    except AccountImportLog.DoesNotExist:
        logger.exception("[Import] Log not found: log_id=%s", log_id)
        return
    logger.info(
        "[Import] Starting import | log_id=%s | file=%s | year=%s | budget=%s | dry_run=%s",
        log_id,
        getattr(log.file, "path", "NO_FILE"),
        log.year,
        log.is_budget,
        log.dry_run,
    )
    log.status = AccountImportLog.Status.STARTED
    log.message = "Import started."
    log.save(update_fields=["status", "message"])

    try:
        logger.info("[Import] Loading dataframe | log_id=%s", log_id)
        account_rows = load_account_dataframe(log.file.path)
        logger.info("[Import] Dataframe loaded | rows=%s | log_id=%s", len(account_rows), log_id)
    except FileNotFoundError:
        logger.exception(
            "[Import] File not found | path=%s | log_id=%s",
            log.file.path,
            log_id,
        )
        log.status = AccountImportLog.Status.FAILED
        log.message = _("The import file could not be found.")
        log.save(update_fields=["status", "message"])
        return
    except Exception as e:
        logger.exception("[Import] Error while loading dataframe | log_id=%s", log_id)
        log.status = AccountImportLog.Status.FAILED
        log.message = f"Error while loading the import file: {e}"
        log.save(update_fields=["status", "message"])
        raise
    mapping_qs = log.column_mappings.all()
    column_map = {m.field: m.column_name for m in mapping_qs}

    logger.info("[Import] Column map | log_id=%s | map=%s", log_id, column_map)
    derived_from_total = any(m.field == "total" and m.derived_from_total for m in mapping_qs)
    logger.info(
        "[Import] Flags | derived_from_total=%s | log_id=%s",
        derived_from_total,
        log_id,
    )

    try:
        logger.info("[Import] Calling importer | log_id=%s", log_id)
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
        logger.info("[Import] Importer finished | log_id=%s", log_id)
    except ValueError as ve:
        logger.warning(
            "[Import] Validation error | log_id=%s | error=%s",
            log_id,
            str(ve),
        )
        log.status = AccountImportLog.Status.FAILED
        log.message = _("Import failed: ") + str(ve)
        log.save(update_fields=["status", "message"])
        return
    except Exception as e:
        logger.exception("[Import] Unexpected error during import | log_id=%s", log_id)
        log.status = AccountImportLog.Status.FAILED
        log.message = _("Unexpected error: ") + str(e)
        log.save(update_fields=["status", "message"])
        logger.exception(f"[Import] Unexpected failure for {log}")
        raise

    logger.info("[Import] Creating AvailableYear | log_id=%s", log_id)
    AvailableYear.objects.get_or_create(
        year=log.year,
        type=(log.is_budget and AvailableYear.YearType.BUDGET) or AvailableYear.YearType.ACTUAL,
    )

    log.status = AccountImportLog.Status.SUCCESS
    log.message = "Import completed successfully."
    log.save(update_fields=["status", "message"])
    logger.info("[Import] SUCCESS | log_id=%s", log_id)
