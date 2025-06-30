import logging
from decimal import Decimal

import pandas as pd

from budgetis.accounting.models import Account
from budgetis.accounting.models import AccountGroup
from budgetis.accounting.models import GroupResponsibility


# The account code string (e.g., '170.301' or '170.301.2')
MIN_PARTS = 2
MAX_PARTS = 3
FUNCTION_PART = 0
NATURE_PART = 1
SUBACCOUNT_PART = 2

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


def import_accounts_from_csv(csv_path: str, year: int, *, is_budget: bool, dry_run: bool = False) -> None:
    """
    Imports account data from a CSV file and updates or creates Account, AccountGroup,
    and GroupResponsibility objects accordingly.

    Args:
        csv_path (str): Path to the CSV file.
        year (int): Target fiscal year.
        is_budget (bool): Whether the data represents a budget or actual accounts.
        dry_run (bool): If True, data is parsed and validated but not saved to the DB.
    """
    logger.info(f"Starting import from {csv_path} for year {year}. Dry-run: {dry_run}")
    account_rows = pd.read_csv(csv_path, dtype=str)
    account_rows = account_rows.fillna("").applymap(lambda x: x.strip() if isinstance(x, str) else x)

    for _, row in account_rows.iterrows():
        group_code = row["groupe"]
        group_label = row["nom du groupe"]
        municipal_name = row["responsable"]
        full_code = row["code"]
        label = row["intitulé"]
        charges = Decimal(row["charges"].replace("'", "") or "0")
        revenues = Decimal(row["produits"].replace("'", "") or "0")

        function, nature, sub_account = parse_account_code(full_code)

        if charges and revenues:
            expected_type = "both"
        elif charges:
            expected_type = "charges"
        elif revenues:
            expected_type = "revenues"
        else:
            expected_type = "charges"

        logger.info(
            f"[{'DRY' if dry_run else 'REAL'}] "
            f"{year} - {group_code} - {function}.{nature}"
            f"{'.' + str(sub_account) if sub_account else ''} - {label}"
        )

        if not dry_run:
            group, _ = AccountGroup.objects.get_or_create(code=group_code, defaults={"label": group_label})

            GroupResponsibility.objects.get_or_create(
                group=group, year=year, defaults={"municipal_name": municipal_name, "responsible": None}
            )

            Account.objects.update_or_create(
                year=year,
                function=function,
                nature=nature,
                sub_account=sub_account,
                is_budget=is_budget,
                defaults={
                    "label": label,
                    "group": group,
                    "charges": charges,
                    "revenues": revenues,
                    "expected_type": expected_type,
                },
            )
    logger.info("Import completed.")
