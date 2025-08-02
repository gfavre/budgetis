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


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


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


def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    return df.fillna("").apply(lambda col: col.map(lambda x: x.strip() if isinstance(x, str) else x))


def build_source_account_map(source_year) -> dict:
    if not source_year:
        return {}

    logger.info(f"Using source year: {source_year}")
    source_accounts = Account.objects.filter(
        year=source_year.year,
        is_budget=source_year.type == source_year.YearType.BUDGET,
    ).select_related("group")

    return {(acc.function, acc.nature, acc.sub_account): acc for acc in source_accounts}


def process_account_row(row, column_map, derived_from_total):
    raw_number = row.get(column_map.get("code", ""), "").strip()
    label = row.get(column_map.get("label", ""), "").strip()

    if not raw_number or not label:
        return None

    try:
        function, nature, sub_account = parse_account_code(raw_number)
    except ValueError:
        logger.warning("Invalid account code: %s", raw_number)
        return None

    if not function or not function.isdigit():
        logger.warning("Non-numeric function: %s", function)
        return None

    if derived_from_total:
        total = Decimal(row.get(column_map.get("total", ""), 0))
        charges = total if total > 0 else Decimal(0)
        revenues = -total if total < 0 else Decimal(0)
    else:
        charges = Decimal(row.get(column_map.get("charges", ""), 0))
        revenues = abs(Decimal(row.get(column_map.get("revenues", ""), 0)))

    expected_type = (
        Account.ExpectedType.BOTH
        if charges and revenues
        else Account.ExpectedType.CHARGE
        if charges
        else Account.ExpectedType.REVENUE
    )

    account_defaults = {
        "label": label,
        "charges": charges,
        "revenues": revenues,
        "expected_type": expected_type,
    }

    return function, nature, sub_account, account_defaults


def apply_source_overrides(defaults, source_acc, copy_labels, copy_visibility):
    if not source_acc:
        return
    if copy_labels:
        defaults["label"] = source_acc.label
    if copy_visibility:
        defaults["visible_in_report"] = source_acc.visible_in_report


def persist_account(year, function, nature, sub_account, is_budget, defaults):  # noqa:PLR0913
    account, _ = Account.objects.update_or_create(
        year=year,
        function=function,
        nature=nature,
        sub_account=sub_account,
        is_budget=is_budget,
        defaults=defaults,
    )
    logger.info(f"Account {year}-{function}.{nature} created/updated.")
    return account


def copy_group_responsibles(account, source_acc, year):
    if not source_acc or not source_acc.group_id:
        return
    for responsibility in source_acc.group.responsibilities.all():
        GroupResponsibility.objects.update_or_create(
            group_id=source_acc.group_id,
            year=year,
            defaults={"responsible": responsibility.responsible},
        )


def copy_account_comments(account, source_acc):
    if not source_acc:
        return
    for comment in source_acc.comments.all():
        AccountComment.objects.update_or_create(
            account=account,
            author=comment.author,
            content=comment.content,
            created_at=comment.created_at,
        )


def import_accounts_from_dataframe(  # noqa: PLR0913
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
    column_map: dict[str, str] | None = None,
    derived_from_total: bool = False,
) -> None:
    logger.info(f"Starting import for year {year}. Dry-run: {dry_run}")
    column_map = column_map or {}

    account_rows = clean_dataframe(account_rows)
    source_accounts = build_source_account_map(source_year)

    for _, row in account_rows.iterrows():
        result = process_account_row(row, column_map, derived_from_total)
        if result is None:
            continue

        function, nature, sub_account, account_defaults = result

        key = (function, nature, sub_account)
        source_acc = source_accounts.get(key)

        apply_source_overrides(account_defaults, source_acc, copy_labels, copy_visibility)

        if not dry_run:
            account = persist_account(year, function, nature, sub_account, is_budget, account_defaults)

            if copy_responsibles:
                copy_group_responsibles(account, source_acc, year)

            if copy_comments:
                copy_account_comments(account, source_acc)

    logger.info(f"Import complete. Total rows processed: {len(account_rows)}.")
