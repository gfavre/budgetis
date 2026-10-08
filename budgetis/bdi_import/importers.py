import logging
from dataclasses import dataclass
from dataclasses import field
from decimal import Decimal

import pandas as pd
from django.contrib.auth import get_user_model
from django.utils.translation import gettext as _

from budgetis.accounting.models import Account
from budgetis.accounting.models import AccountComment
from budgetis.accounting.models import GroupResponsibility
from budgetis.common.models import ChartScheme

from .models import ColumnMapping
from .utils import safe_decimal


# The account code string (e.g., '170.301' or '170.301.2')
MIN_PARTS = 2
MAX_PARTS = 3
FUNCTION_PART = 0
NATURE_PART = 1
SUBACCOUNT_PART = 2

# How many offending codes are quoted in an import log's message.
INVALID_CODE_EXAMPLES = 5


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class InvalidAccountCodeError(ValueError):
    """A row has an account code, but it cannot be read as one."""

    def __init__(self, raw_code: str):
        self.raw_code = raw_code
        super().__init__(f"Invalid account code: {raw_code}")


@dataclass
class ImportResult:
    rows: int = 0
    accounts: int = 0
    invalid_codes: list[str] = field(default_factory=list)


def validate_column_map(column_map: dict[str, str]) -> None:
    """
    Rejects a mapping that cannot identify accounts. Mapping a column to the
    combined "Account code" next to separate function/nature columns makes
    every row fall into the combined-code path, where a bare nature such as
    "3000" is not a valid code - each row is skipped and nothing is imported.
    """
    has_code = ColumnMapping.Field.CODE in column_map
    has_split = ColumnMapping.Field.FUNCTION in column_map or ColumnMapping.Field.NATURE in column_map
    if has_code and has_split:
        message = _(
            '"%(code)s" is for a single column holding the full code (e.g. 170.301.2). '
            'It cannot be combined with "%(function)s" / "%(nature)s" columns.'
        ) % {
            "code": ColumnMapping.Field.CODE.label,
            "function": ColumnMapping.Field.FUNCTION.label,
            "nature": ColumnMapping.Field.NATURE.label,
        }
        raise ValueError(message)
    if has_split and not (ColumnMapping.Field.FUNCTION in column_map and ColumnMapping.Field.NATURE in column_map):
        message = _('"%(function)s" and "%(nature)s" must both be mapped.') % {
            "function": ColumnMapping.Field.FUNCTION.label,
            "nature": ColumnMapping.Field.NATURE.label,
        }
        raise ValueError(message)
    if not has_code and not has_split:
        message = _('Map either "%(code)s" or both "%(function)s" and "%(nature)s".') % {
            "code": ColumnMapping.Field.CODE.label,
            "function": ColumnMapping.Field.FUNCTION.label,
            "nature": ColumnMapping.Field.NATURE.label,
        }
        raise ValueError(message)


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
    return function, nature, _normalize_sub_account(sub_account)


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
        except ValueError as exc:
            raise InvalidAccountCodeError(raw_number) from exc

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


def _move_negative_to_opposite_side(charges: Decimal, revenues: Decimal) -> tuple[Decimal, Decimal]:
    """
    A negative charge is a credit (e.g. 3010.99 "remboursements d'assurances")
    and a negative revenue is a debit: MCH2 statements show each in the
    opposite column, so store them there as positive amounts.
    """
    if charges < 0:
        revenues, charges = revenues - charges, Decimal(0)
    if revenues < 0:
        charges, revenues = charges - revenues, Decimal(0)
    return charges, revenues


def process_account_row(row, column_map, derived_from_total, scheme=ChartScheme.MCH1, *, positive_revenues=False):
    label = row.get(column_map.get("label", ""), "").strip()
    if not label:
        return None

    code = _extract_account_code(row, column_map)
    if code is None:
        return None
    function, nature, sub_account = code

    if not function or not function.isdigit():
        raw_code = f"{function}.{nature}"
        raise InvalidAccountCodeError(raw_code)

    if derived_from_total:
        total = safe_decimal(row.get(column_map.get("total", ""), 0))
        charges = total if total > 0 else Decimal(0)
        revenues = -total if total < 0 else Decimal(0)
    else:
        charges = safe_decimal(row.get(column_map.get("charges", ""), 0))
        revenues = safe_decimal(row.get(column_map.get("revenues", ""), 0))
        if not positive_revenues:
            revenues = -revenues
        charges, revenues = _move_negative_to_opposite_side(charges, revenues)

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
    if not source_acc or not source_acc.group_id or not account.group_id:
        return
    for responsibility in source_acc.group.responsibilities.filter(
        year=source_acc.year, function__in=("", source_acc.function)
    ):
        GroupResponsibility.objects.update_or_create(
            group_id=account.group_id,
            function=account.function if responsibility.function else "",
            year=year,
            defaults={"responsible": responsibility.responsible},
        )


def assign_row_responsible(account, row, column_map, year):
    """Map a per-row responsible trigram (e.g. a manually-prepared budget
    sheet's own "Resp BUD" column) onto its function for this year."""
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
        function=account.function if account.scheme == ChartScheme.MCH2 else "",
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


def _accumulate_rows(  # noqa: PLR0913
    account_rows, column_map, derived_from_total, scheme, invalid_codes, *, positive_revenues=False
):
    """
    Group parsed rows by (function, nature, sub_account) and sum their charges/
    revenues. A manually-prepared sheet can have several MCH1-origin rows
    collapsing onto the same MCH2 target (a merge) - their amounts must add up,
    not have the last one silently overwrite the others. The first row seen for
    a key is kept as the representative row (label, responsible column).
    """
    accumulated: dict[tuple[str, str, str], dict] = {}
    for _index, row in account_rows.iterrows():
        try:
            result = process_account_row(
                row, column_map, derived_from_total, scheme, positive_revenues=positive_revenues
            )
        except InvalidAccountCodeError as exc:
            logger.warning("Invalid account code: %s", exc.raw_code)
            invalid_codes.append(exc.raw_code)
            continue
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
    positive_revenues: bool = False,
) -> ImportResult:
    logger.info(f"Starting import for year {year}. Dry-run: {dry_run}")
    column_map = column_map or {}
    validate_column_map(column_map)
    result = ImportResult(rows=len(account_rows))

    account_rows = clean_dataframe(account_rows)
    source_accounts = build_source_account_map(source_year)
    accumulated = _accumulate_rows(
        account_rows, column_map, derived_from_total, scheme, result.invalid_codes, positive_revenues=positive_revenues
    )
    result.accounts = len(accumulated)

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
    return result
