import sys

import pandas as pd
from django.core.management.base import CommandError


def read_excel_sheet(excel_path, sheet_name: str, **read_excel_kwargs) -> pd.DataFrame:
    """
    Wraps pandas.read_excel with a readable fallback when the sheet doesn't
    exist - the wrong file (or a renamed sheet) is a one-line mistake to make.
    In an interactive terminal, offers a numbered pick among the sheets the
    file actually has; otherwise (scripts, tests) raises a CommandError
    listing them instead of pandas' raw traceback.
    """
    try:
        return pd.read_excel(excel_path, sheet_name=sheet_name, **read_excel_kwargs)
    except ValueError as error:
        if "Worksheet named" not in str(error):
            raise
        available = pd.ExcelFile(excel_path).sheet_names
        chosen = _prompt_for_sheet(sheet_name, available) if sys.stdin.isatty() else None
        if chosen is None:
            message = f"Sheet '{sheet_name}' not found in {excel_path}. Available sheets: {', '.join(available)}"
            raise CommandError(message) from error
        return pd.read_excel(excel_path, sheet_name=chosen, **read_excel_kwargs)


def _prompt_for_sheet(expected_name: str, available: list[str]) -> str | None:
    menu = "\n".join(
        [
            f"Sheet '{expected_name}' not found. Pick one instead (Enter to cancel):",
            *(f"  {index}. {name}" for index, name in enumerate(available, start=1)),
            "> ",
        ]
    )
    choice = input(menu).strip()
    if not choice.isdigit():
        return None
    index = int(choice)
    if 1 <= index <= len(available):
        return available[index - 1]
    return None
