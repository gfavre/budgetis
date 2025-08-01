import logging
from decimal import Decimal

import pandas as pd

from budgetis.accounting.models import Account
from budgetis.accounting.models import AccountComment
from budgetis.accounting.models import GroupResponsibility


# The account code string (e.g., '170.301' or '170.301.2')
MIN_PARTS = 2
MAX_PARTS = 3
FUNCTION_PART = 0
NATURE_PART = 1
SUBACCOUNT_PART = 2

ACCOUNT_NUMBER_COLUMN = "CPT_NUM_CPT"
ACCOUNT_LABEL_COLUMN = "CPT_LIB"
ACCOUNT_TOTAL_COLUMN = "Solde"  # Positive: charges, Negative: Revenues
ACCOUNT_CHARGES_COLUMN = "SLDE_DEB"
ACCOUNT_REVENUES_COLUMN = "SLDE_CRE"
ACCOUNT_GROUP_CODE_COLUMN = "CPT_COD_CLAS"

logger = logging.getLogger(__name__)


def parse_account_code(code: str) -> tuple[str, str, str]:
    """
    Parses a code string of the form 'function.nature[.subaccount]'.

    Args:
        code: The account code string (e.g., '170.301' or '170.301.2').

    Returns:
        A tuple (function, nature, sub_account), where sub_account can be None.

    Raises:
        ValueError: If the input format is invalid or cannot be parsed as integers.
    """
    parts = code.strip().split(".")
    if not (MIN_PARTS <= len(parts) <= MAX_PARTS):
        message = f"Invalid account code: {code}"
        raise ValueError(message)
    function = parts[FUNCTION_PART]
    nature = parts[NATURE_PART]
    sub_account = parts[SUBACCOUNT_PART] if len(parts) == MAX_PARTS else ""
    return function, nature, sub_account


def import_accounts_from_dataframe(  # noqa: C901, PLR0913, PLR0912
    account_rows: pd.DataFrame,
    year: int,
    *,
    is_budget: bool,
    dry_run: bool = False,
    source_year=None,
    copy_responsibles: bool = True,
    copy_labels: bool = True,
    copy_visibility: bool = True,
    copy_comments: bool = True,
) -> None:
    """
    Imports account data and optionally copies attributes from a source year.

    Args:
        account_rows: DataFrame to import
        year: Target fiscal year
        is_budget: Whether the data is for budget
        dry_run: If True, don't write to DB
        source_year: AvailableYear instance to copy from (same type)
        copy_responsibles: Copy group responsibilities
        copy_labels: Copy account labels
        copy_visibility: Copy visibility flag
        copy_comments: Copy account comments
    """
    logger.info(f"Starting import from dataframe for year {year}. Dry-run: {dry_run}")

    account_rows = account_rows.fillna("").applymap(lambda x: x.strip() if isinstance(x, str) else x)

    source_accounts_by_key = {}
    if source_year:
        logger.info(f"Using source year: {source_year}")
        source_accounts = Account.objects.filter(
            year=source_year.year,
            is_budget=source_year.type == source_year.YearType.BUDGET,
        ).select_related("group")

        for acc in source_accounts:
            key = (acc.function, acc.nature, acc.sub_account)
            source_accounts_by_key[key] = acc

    for _, row in account_rows.iterrows():
        raw_number = row.get(ACCOUNT_NUMBER_COLUMN, "").strip()
        label = row.get(ACCOUNT_LABEL_COLUMN, "").strip()

        if not raw_number or not label:
            continue

        try:
            function, nature, sub_account = parse_account_code(raw_number)
        except ValueError:
            logger.warning("Skipping row with invalid account code: %s", row.get(ACCOUNT_NUMBER_COLUMN, "<?>"))
            continue
        if not function.isdigit():
            logger.warning("Skipping row with non-numeric function: %s", function)
            continue
        total = Decimal(row.get(ACCOUNT_TOTAL_COLUMN, 0))
        if total < 0:
            revenues = Decimal(-total)
            charges = Decimal(0)
            expected_type = Account.ExpectedType.REVENUE
        else:
            revenues = Decimal(0)
            charges = Decimal(total)
            expected_type = Account.ExpectedType.CHARGE

        account_defaults = {
            "charges": charges,
            "revenues": revenues,
            "expected_type": expected_type,
            "label": label,
        }
        # Optionally override from source account
        key = (function, nature, sub_account)
        source_acc = source_accounts_by_key.get(key)
        if source_acc:
            if copy_labels:
                account_defaults["label"] = source_acc.label
            if copy_visibility:
                account_defaults["visible_in_report"] = source_acc.visible_in_report

        logger.info(
            f"[{'DRY' if dry_run else 'REAL'}] {year} - {function}.{nature}"
            f"{'.' + str(sub_account) if sub_account else ''} - {account_defaults['label']}"
        )
        if not dry_run:
            account, created = Account.objects.update_or_create(
                year=year,
                function=function,
                nature=nature,
                sub_account=sub_account,
                is_budget=is_budget,
                defaults=account_defaults,
            )

            if copy_responsibles and source_acc and source_acc.group_id:
                for responsibility in source_acc.group.responsibilities.all():
                    GroupResponsibility.objects.update_or_create(
                        group_id=source_acc.group_id,
                        year=year,
                        defaults={"responsible": responsibility.responsible},
                    )
                logger.info("Responsibles for group copied")

            if copy_comments and source_acc:
                for comment in source_acc.comments.all():
                    AccountComment.objects.update_or_create(
                        account=account,
                        author=comment.author,
                        content=comment.content,
                        created_at=comment.created_at,
                    )
            logger.info(f"Account import completed for year {year}. Total accounts processed: {len(account_rows)}.")

    logger.info("Account import completed.")
