from pathlib import Path

import pandas as pd


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
        exception_message = f"Unsupported file extension: {extension}. Supported extensions are .csv and .xlsx."
        raise ValueError(exception_message)

    return dataframe.fillna("").applymap(lambda x: x.strip() if isinstance(x, str) else x)
