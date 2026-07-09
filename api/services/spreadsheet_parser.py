"""Spreadsheet parsing service.

Handles .xlsx, .xls, and .csv files with freeform customer layouts:
- Auto-detects whether row 0 is a title (fewer than 2 non-null values) and
  falls back to row 1 as the header row.
- Strips whitespace and normalises column names.
- Forward-fills merged-cell values.
- Drops all-null rows and columns whose header is empty/None.
- Converts all values to JSON-serialisable Python native types (no numpy types,
  no NaT, no NaN).
"""
import io
import logging
import math
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

# Accepted MIME types / extensions
ALLOWED_EXTENSIONS = {".xlsx", ".xls", ".csv"}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB


def _to_python(value: Any) -> Any:
    """Convert a single cell value to a JSON-serialisable Python native type."""
    if value is None:
        return None
    # pandas NA / NaT / NaN sentinel
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    # numpy integer types
    if hasattr(value, "item"):
        try:
            value = value.item()
        except Exception:
            pass
    # float NaN / inf that survived .item()
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    # pandas Timestamp / datetime-like
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _clean_column_name(name: Any) -> str | None:
    """Return a clean string column name, or None if effectively empty."""
    if name is None:
        return None
    cleaned = str(name).strip().replace("\n", " ").replace("\r", "")
    return cleaned if cleaned else None


def _read_dataframe(file_bytes: bytes, filename: str, header_row: int) -> pd.DataFrame:
    """Read the file into a DataFrame using the given header row index."""
    lower = filename.lower()
    buf = io.BytesIO(file_bytes)

    if lower.endswith(".csv"):
        df = pd.read_csv(buf, header=header_row, dtype=str, keep_default_na=False)
    else:
        df = pd.read_excel(
            buf,
            header=header_row,
            dtype=object,
            engine="openpyxl" if lower.endswith(".xlsx") else None,
        )
    return df


def parse_spreadsheet(file_bytes: bytes, filename: str) -> list[dict]:
    """Parse an uploaded spreadsheet and return a list of row dicts.

    Each dict uses cleaned column names as keys and JSON-serialisable values.
    Raises ValueError for files that cannot be parsed.
    """
    if len(file_bytes) > MAX_FILE_SIZE:
        raise ValueError(
            f"File exceeds maximum allowed size of 50 MB "
            f"(received {len(file_bytes) / 1024 / 1024:.1f} MB)"
        )

    lower = filename.lower()
    ext = "." + lower.rsplit(".", 1)[-1] if "." in lower else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )

    # --- First pass with header=0 -----------------------------------------
    df = _read_dataframe(file_bytes, filename, header_row=0)

    # Detect title row: if the first data row has fewer than 2 non-null values
    # the presumed "header" (row 0) is likely a title / banner row.
    if len(df.columns) >= 2:
        non_null_headers = sum(
            1 for c in df.columns if _clean_column_name(c) is not None
        )
        if non_null_headers < 2:
            logger.info(
                "Header row 0 appears to be a title (%d non-null columns); "
                "re-reading with header=1",
                non_null_headers,
            )
            df = _read_dataframe(file_bytes, filename, header_row=1)

    # --- Clean column names ---------------------------------------------------
    renamed: dict[Any, str | None] = {col: _clean_column_name(col) for col in df.columns}
    # Keep only columns whose cleaned name is non-empty
    good_cols = [orig for orig, clean in renamed.items() if clean]
    df = df[good_cols].copy()
    df.rename(columns={orig: renamed[orig] for orig in good_cols}, inplace=True)

    # --- Forward-fill (handles merged cells in Excel) -------------------------
    df.ffill(inplace=True)

    # --- Drop all-null rows ---------------------------------------------------
    df.dropna(how="all", inplace=True)

    # --- Convert values -------------------------------------------------------
    rows: list[dict] = []
    for _, row in df.iterrows():
        record = {col: _to_python(val) for col, val in row.items()}
        # Skip rows that are entirely None after conversion
        if all(v is None for v in record.values()):
            continue
        rows.append(record)

    logger.info("Parsed %d rows from '%s'", len(rows), filename)
    return rows
