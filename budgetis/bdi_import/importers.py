import logging
from decimal import Decimal

import pandas as pd
from django.contrib.auth import get_user_model

from budgetis.accounting.models import Account
from budgetis.accounting.models import AccountComment
from budgetis.accounting.models import GroupResponsibility
from budgetis.common.models import ChartScheme

from .utils import safe_decimal


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
    cleaned_code = code.strip().replace(",", ".")
    parts = cleaned_code.split(".")
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


def _normalize_sub_account(value: str) -> str:
    """An all-zero sub-account ("0", "00"...) means "no sub-account" - same
    convention used everywhere else in this project (e.g. import_mch2_accounts)."""
    value = value.strip()
    return "" if value.isdigit() and int(value) == 0 else value


def _extract_account_code(row, column_map) -> tuple[str, str, str] | None:
    """
    Returns (function, nature, sub_account), reading either a single combined
    "function.nature[.sub]" column (the historical BDI-export shape) or three
    separate columns (a manually-prepared sheet, e.g. Fctio/Nat/Ext MCH2).
    """
    if "code" in column_map:
        raw_number = row.get(column_map["code"], "").strip()
        if not raw_number:
            return None
        try:
            return parse_account_code(raw_number)
        except ValueError:
            logger.warning("Invalid account code: %s", raw_number)
            return None

    if "function" in column_map and "nature" in column_map:
        function = row.get(column_map["function"], "").strip()
        nature = row.get(column_map["nature"], "").strip()
        if not function or not nature:
            return None
        sub_account = _normalize_sub_account(row.get(column_map.get("sub_account", ""), ""))
        return function, nature, sub_account

    return None


def _expected_type(charges: Decimal, revenues: Decimal) -> str:
    if charges and revenues:
        return Account.ExpectedType.BOTH
    if charges:
        return Account.ExpectedType.CHARGE
    return Account.ExpectedType.REVENUE


def process_account_row(row, column_map, derived_from_total, scheme=ChartScheme.MCH1):
    label = row.get(column_map.get("label", ""), "").strip()
    if not label:
        return None

    code = _extract_account_code(row, column_map)
    if code is None:
        return None
    function, nature, sub_account = code

    if not function or not function.isdigit():
        logger.warning("Non-numeric function: %s", function)
        return None

    if derived_from_total:
        total = safe_decimal(row.get(column_map.get("total", ""), 0))
        charges = total if total > 0 else Decimal(0)
        revenues = -total if total < 0 else Decimal(0)
    else:
        charges = safe_decimal(row.get(column_map.get("charges", ""), 0))
        revenues = -safe_decimal(row.get(column_map.get("revenues", ""), 0))

    expected_type = _expected_type(charges, revenues)

    account_defaults = {
        "label": label,
        "charges": charges,
        "revenues": revenues,
        "expected_type": expected_type,
        "scheme": scheme,
    }

    return function, nature, sub_account, account_defaults


def apply_source_overrides(defaults, source_acc, copy_labels, copy_visibility):
    if not source_acc:
        return
    if copy_labels:
        defaults["label"] = source_acc.label
    if copy_visibility:
        defaults["visible_in_report"] = source_acc.visible_in_report


def persist_account(year, function, nature, sub_account, is_budget, defaults):  # noqa: PLR0913, PLR0917
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


def assign_row_responsible(account, row, column_map, year):
    """Map a per-row responsible trigram (e.g. a manually-prepared budget
    sheet's own "Resp BUD" column) onto the account's group for this year."""
    if "responsible" not in column_map or not account.group_id:
        return

    trigram = row.get(column_map["responsible"], "").strip().upper()
    if not trigram:
        return

    user = get_user_model().objects.filter(trigram=trigram).first()
    if not user:
        logger.warning("Unknown trigram: %s", trigram)
        return

    GroupResponsibility.objects.update_or_create(
        group=account.group,
        year=year,
        defaults={"responsible": user},
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


def _accumulate_rows(account_rows, column_map, derived_from_total, scheme):
    """
    Group parsed rows by (function, nature, sub_account) and sum their charges/
    revenues. A manually-prepared sheet can have several MCH1-origin rows
    collapsing onto the same MCH2 target (a merge) - their amounts must add up,
    not have the last one silently overwrite the others. The first row seen for
    a key is kept as the representative row (label, responsible column).
    """
    accumulated: dict[tuple[str, str, str], dict] = {}
    for _, row in account_rows.iterrows():
        result = process_account_row(row, column_map, derived_from_total, scheme)
        if result is None:
            continue

        function, nature, sub_account, account_defaults = result
        key = (function, nature, sub_account)

        if key not in accumulated:
            accumulated[key] = {"defaults": account_defaults, "row": row}
        else:
            existing = accumulated[key]["defaults"]
            existing["charges"] += account_defaults["charges"]
            existing["revenues"] += account_defaults["revenues"]
            existing["expected_type"] = _expected_type(existing["charges"], existing["revenues"])

    return accumulated


def import_accounts_from_dataframe(  # noqa: PLR0913
    account_rows: pd.DataFrame,
    year: int,
    *,
    is_budget: bool,
    scheme: str = ChartScheme.MCH1,
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
    accumulated = _accumulate_rows(account_rows, column_map, derived_from_total, scheme)

    for (function, nature, sub_account), entry in accumulated.items():
        account_defaults = entry["defaults"]
        row = entry["row"]
        source_acc = source_accounts.get((function, nature, sub_account))

        apply_source_overrides(account_defaults, source_acc, copy_labels, copy_visibility)

        if not dry_run:
            account = persist_account(year, function, nature, sub_account, is_budget, account_defaults)

            if copy_responsibles:
                copy_group_responsibles(account, source_acc, year)

            assign_row_responsible(account, row, column_map, year)

            if copy_comments:
                copy_account_comments(account, source_acc)

    logger.info(f"Import complete. Total rows processed: {len(account_rows)}.")
