import logging
from decimal import Decimal

import pandas as pd

from budgetis.accounting.models import Account


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


def parse_account_code(code: str) -> tuple[int, int, int | None]:
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
    function = int(parts[FUNCTION_PART])
    nature = int(parts[NATURE_PART])
    sub_account = int(parts[SUBACCOUNT_PART]) if len(parts) == MAX_PARTS else None
    return function, nature, sub_account


def import_accounts_from_dataframe(
    account_rows: pd.DataFrame, year: int, *, is_budget: bool, dry_run: bool = False
) -> None:
    """
    Imports account data from a CSV file and updates or creates Account, AccountGroup,
    and GroupResponsibility objects accordingly.

    Args:
        account_rows (Panda Dataframe): the dataframe to import.
        year (int): Target fiscal year.
        is_budget (bool): Whether the data represents a budget or actual accounts.
        dry_run (bool): If True, data is parsed and validated but not saved to the DB.
    """
    logger.info(f"Starting import from dataframe for year {year}. Dry-run: {dry_run}")

    account_rows = account_rows.fillna("").applymap(lambda x: x.strip() if isinstance(x, str) else x)
    for _, row in account_rows.iterrows():
        raw_number = row.get(ACCOUNT_NUMBER_COLUMN, "").strip()
        label = row.get(ACCOUNT_LABEL_COLUMN, "").strip()

        if not raw_number or not label:
            continue

        try:
            function, nature, sub_account = parse_account_code(raw_number)
        except ValueError:
            logger.exception(f"Skipping row due to parsing error. Row data: {row.to_dict()}")
            continue

        total = Decimal(row.get(ACCOUNT_TOTAL_COLUMN, 0))
        if total < 0:
            revenues = Decimal(-total)
            charges = Decimal(0)
            expected_type = "revenues"
        else:
            revenues = Decimal(0)
            charges = Decimal(total)
            expected_type = "charges"

        logger.info(
            f"[{'DRY' if dry_run else 'REAL'}] "
            f"{year} - {function}.{nature}"
            f"{'.' + str(sub_account) if sub_account else ''} - {label}"
        )
        if not dry_run:
            Account.objects.update_or_create(
                year=year,
                function=function,
                nature=nature,
                sub_account=sub_account,
                is_budget=is_budget,
                defaults={
                    "label": label,
                    "charges": charges,
                    "revenues": revenues,
                    "expected_type": expected_type,
                },
            )
    logger.info("Import completed.")
