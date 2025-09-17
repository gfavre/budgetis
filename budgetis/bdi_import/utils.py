from decimal import Decimal
from decimal import InvalidOperation
from pathlib import Path

import pandas as pd
from django.utils.translation import gettext as _


def safe_decimal(value, default: Decimal = Decimal(0)) -> Decimal:
    """
    Convert a value into Decimal safely.

    Args:
        value: Input value (str, int, float, etc.).
        default (Decimal): Value to return if conversion fails.

    Returns:
        Decimal: Converted value or the default.
    """
    if value is None:
        return default
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError, TypeError):
        return default


def detect_first_data_row(df: pd.DataFrame, min_fields: int = 3) -> int:
    for idx, row in df.iterrows():
        nonempty = row.dropna().astype(str).str.strip()
        if (nonempty != "").sum() >= min_fields:
            return idx
    msg = "No usable header row found."
    raise ValueError(msg)


def load_account_dataframe(path: str) -> pd.DataFrame:
    """
    Load a CSV or XLSX file into a cleaned DataFrame (string values only).
    """
    extension = Path(path).suffix.lower()
    if extension == ".csv":
        try:
            dataframe = pd.read_csv(path, encoding="utf-8", sep=";", dtype=str)
        except UnicodeDecodeError:
            dataframe = pd.read_csv(path, encoding="latin1", sep=";", dtype=str)
    elif extension == ".xlsx":
        dataframe = pd.read_excel(path, dtype=str)
    else:
        exception_message = _(
            "Unsupported file extension: %(extension)s. Supported extensions are .csv and .xlsx.",
            {"extension": extension},
        )
        raise ValueError(exception_message)

    return dataframe.fillna("").applymap(lambda x: x.strip() if isinstance(x, str) else x)


def load_dataframe_with_header(path: str) -> pd.DataFrame:
    """
    Load a CSV or XLSX file into a pandas DataFrame with the proper header row detected.

    Args:
        path (str): Path to the uploaded file.

    Returns:
        pd.DataFrame: DataFrame with detected header row applied.

    Raises:
        ValueError: If the file type is unsupported or no valid data rows are found.
    """
    is_xlsx = path.endswith(".xlsx")

    # Load raw file without header
    raw_df = pd.read_excel(path, sheet_name=0, header=None) if is_xlsx else pd.read_csv(path, header=None)
    header_row = detect_first_data_row(raw_df)

    # Reload with detected header
    return pd.read_excel(path, sheet_name=0, header=header_row) if is_xlsx else pd.read_csv(path, header=header_row)


def find_first_significant_content_row(df: pd.DataFrame, min_valid_fields: int = 4) -> int:
    """
    Detect the first row with at least `min_valid_fields` non-empty, non-zero values.

    Args:
        df (pd.DataFrame): DataFrame already loaded with header row.
        min_valid_fields (int): Minimum number of significant values to count row as valid.

    Returns:
        int: Index of the first significant row.

    Raises:
        ValueError: If no such row is found.
    """

    def is_significant(val: str) -> bool:
        return val.strip().lower() not in {"", "0", "0.0", "nan"}

    for idx, row in df.iterrows():
        str_values = row.dropna().astype(str)
        if sum(is_significant(v) for v in str_values) >= min_valid_fields:
            return idx
    exception_message = _("No sufficiently filled data row found.")
    raise ValueError(exception_message)
