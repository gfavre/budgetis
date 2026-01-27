from __future__ import annotations

import argparse
import logging
import re
from pathlib import Path

import pandas as pd


DELIMITER = "\t"
ENCODING_SOURCE = "cp1252"
ENCODING_TARGET = "cp1252"

STREET_PREFIXES_PATTERN = re.compile(
    r"^(?:"
    r"(?:chemin|ch\.|route|rue)"
    r"(?:\s+(?:de la|du|des|de))?"
    r")\s+",
    flags=re.IGNORECASE,
)
logger = logging.getLogger(__name__)


def load_file(path: str) -> pd.DataFrame:
    """
    Load a TSV file containing water meter data.

    Args:
        path (str): Path to the input file.

    Returns:
        pd.DataFrame: Loaded DataFrame with all values as strings.
    """
    return pd.read_csv(
        path,
        sep=DELIMITER,
        dtype=str,
        encoding=ENCODING_SOURCE,
        keep_default_na=False,
        header=None,
    )


def remove_invalid_meter_ids(df: pd.DataFrame, column_index: int) -> tuple[pd.DataFrame, list[str]]:
    """
    Remove rows where the meter identifier length differs from the majority.

    Args:
        df (pd.DataFrame): Input DataFrame.
        column_index (int): Index of the meter ID column.

    Returns:
        Tuple[pd.DataFrame, List[str]]:
            - Cleaned DataFrame.
            - List of removed meter IDs.
    """
    meter_ids = df.iloc[:, column_index].astype(str)
    lengths = meter_ids.str.len()
    common_length = lengths.mode().iloc[0]

    invalid_mask = lengths != common_length
    removed_ids = meter_ids[invalid_mask].tolist()

    return df.loc[~invalid_mask].copy(), removed_ids


def deduplicate_by_meter_id(df: pd.DataFrame, column_index: int) -> pd.DataFrame:
    """
    Keep only the last occurrence of each meter ID.

    Args:
        df (pd.DataFrame): Input DataFrame.
        column_index (int): Index of the meter ID column.

    Returns:
        pd.DataFrame: Deduplicated DataFrame.
    """
    meter_column = df.columns[column_index]
    return df.drop_duplicates(subset=meter_column, keep="last")


def normalize_street_name(value: str) -> str:
    """
    Normalize street names by removing common prefixes.

    Args:
        value (str): Raw street name.

    Returns:
        str: Normalized street name.
    """
    return STREET_PREFIXES_PATTERN.sub("", value).strip()


def split_street_number(value: str) -> tuple[int, int, str]:
    """
    Split a street number into sortable components.

    Returns:
        Tuple[int, int, str]:
            - base number
            - kind rank (simple < composite < suffix)
            - suffix or range (for stable ordering)
    """
    raw = value.strip().lower()

    # Simple number: "2"
    if match := re.fullmatch(r"\d+", raw):
        return int(match.group()), 0, ""

    # Composite or range: "2+4", "4à10", "4-10"
    if match := re.fullmatch(r"(\d+)\s*(?:\+|à|-)\s*\d+", raw):
        return int(match.group(1)), 1, raw

    # Suffix: "2a", "4b"
    if match := re.fullmatch(r"(\d+)\s*([a-z]+)", raw):
        return int(match.group(1)), 2, match.group(2)

    # Fallback (unknown format)
    return 0, 9, raw


def sort_by_street_and_number(
    p_df: pd.DataFrame,
    street_col_index: int,
    number_col_index: int,
) -> pd.DataFrame:
    """
    Sort the DataFrame by street name and logical street number order.

    Args:
        p_df (pd.DataFrame): Input DataFrame.
        street_col_index (int): Index of the street name column.
        number_col_index (int): Index of the street number column.

    Returns:
        pd.DataFrame: Sorted DataFrame.
    """
    # Normalize street name IN PLACE
    p_df.iloc[:, street_col_index] = p_df.iloc[:, street_col_index].astype(str).map(normalize_street_name)

    number_parts = p_df.iloc[:, number_col_index].map(split_street_number)
    p_df["_base"] = number_parts.map(lambda x: x[0])
    p_df["_kind"] = number_parts.map(lambda x: x[1])
    p_df["_extra"] = number_parts.map(lambda x: x[2])

    p_df = p_df.sort_values(
        by=[
            p_df.columns[street_col_index],
            "_base",
            "_kind",
            "_extra",
        ],
        ascending=True,
        kind="mergesort",
    )

    return p_df.drop(columns=["_base", "_kind", "_extra"])


def parse_args() -> argparse.Namespace:
    """
    Parse command-line arguments.

    Returns:
        argparse.Namespace: Parsed arguments.
    """
    parser = argparse.ArgumentParser(
        description="Clean and sort water meter readings (TSV format).",
    )
    parser.add_argument(
        "input_file",
        type=Path,
        help="Path to the input TSV file.",
    )
    parser.add_argument(
        "-o",
        "--output-file",
        type=Path,
        help="Path to the output TSV file. Defaults to '<input>_cleaned.tsv'.",
    )

    return parser.parse_args()


def main() -> None:
    """
    Run the full cleaning and sorting pipeline.
    """
    args = parse_args()
    input_file: Path = args.input_file
    output_file: Path = args.output_file if args.output_file else input_file.with_stem(f"{input_file.stem}_cleaned")

    p_df = load_file(input_file)

    p_df, removed_meter_ids = remove_invalid_meter_ids(p_df, column_index=0)
    p_df = deduplicate_by_meter_id(p_df, column_index=0)

    if removed_meter_ids:
        logger.warning("Removed meter IDs with invalid length:")
        for meter_id in removed_meter_ids:
            logger.warning(f" - {meter_id}")

    p_df = sort_by_street_and_number(
        p_df,
        street_col_index=8,
        number_col_index=9,
    )

    p_df.to_csv(output_file, sep=DELIMITER, index=False, header=False, encoding=ENCODING_TARGET)


if __name__ == "__main__":
    main()
