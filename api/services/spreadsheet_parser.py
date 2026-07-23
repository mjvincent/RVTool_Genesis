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
import zipfile
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

# Accepted MIME types / extensions
ALLOWED_EXTENSIONS = {".xlsx", ".xls", ".csv"}
MAX_FILE_SIZE = 50 * 1024 * 1024           # 50 MB  — checked before any parsing
MAX_UNCOMPRESSED_BYTES = 500 * 1024 * 1024  # 500 MB — guards against zip-bomb XLSX
MAX_DECOMPRESSION_RATIO = 100               # reject any single ZIP member > 100× compressed size
MAX_ROWS = 100_000                          # hard ceiling on parsed rows


def _to_python(value: Any) -> Any:
    """Convert a single cell value to a JSON-serialisable Python native type.

    Returns None for any value that is effectively empty (None, NaN, empty/whitespace string).
    """
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
    # Empty or whitespace-only strings — treat as None so phantom Excel rows are dropped
    if isinstance(value, str) and not value.strip():
        return None
    return value


def _clean_column_name(name: Any) -> str | None:
    """Return a clean string column name, or None if effectively empty."""
    if name is None:
        return None
    cleaned = str(name).strip().replace("\n", " ").replace("\r", "")
    return cleaned if cleaned else None


def _check_xlsx_zip_safety(file_bytes: bytes) -> None:
    """Reject XLSX files that look like zip bombs.

    XLSX is a ZIP archive. A crafted file can be well under 50 MB compressed
    but expand to gigabytes in memory. This guard iterates the ZIP member list
    (which does not decompress anything) and raises ValueError if:

    - The total uncompressed size of all members exceeds MAX_UNCOMPRESSED_BYTES.
    - Any single member has a decompression ratio above MAX_DECOMPRESSION_RATIO
      (only checked for members that are meaningfully compressed, ≥ 1 KB).
    """
    try:
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
            total_uncompressed = 0
            for info in zf.infolist():
                total_uncompressed += info.file_size
                if total_uncompressed > MAX_UNCOMPRESSED_BYTES:
                    raise ValueError(
                        f"File rejected: uncompressed content exceeds "
                        f"{MAX_UNCOMPRESSED_BYTES // (1024 * 1024)} MB limit."
                    )
                if info.compress_size >= 1024 and info.file_size > 0:
                    ratio = info.file_size / info.compress_size
                    if ratio > MAX_DECOMPRESSION_RATIO:
                        raise ValueError(
                            f"File rejected: ZIP member '{info.filename}' has a "
                            f"decompression ratio of {ratio:.0f}× "
                            f"(limit {MAX_DECOMPRESSION_RATIO}×). "
                            "This file may be a zip bomb."
                        )
    except zipfile.BadZipFile:
        # openpyxl will surface a more informative error later; don't shadow it here
        pass


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


def parse_spreadsheet(
    file_bytes: bytes,
    filename: str,
) -> dict[str, Any]:
    """Parse an uploaded spreadsheet and return a result dict with keys:

    - ``rows``: list of row dicts (cleaned column names + JSON-serialisable
      values). Every row also contains the reserved key ``_row_number`` (int)
      that holds the **absolute spreadsheet row number** matching what Excel
      shows in its row gutter (1-based, header row = 1 or 2 depending on title
      detection). This lets the UI display "Row 7 in your spreadsheet" on
      failed/incomplete records so the user can locate the problem in the
      original file.
    - ``columns``: list of cleaned column names (excluding ``_row_number``).
    - ``sample_rows``: first 5 row dicts, each without the ``_row_number`` key.

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

    # --- XLSX zip-bomb guard (must come after extension check) ---------------
    if ext in {".xlsx", ".xls"}:
        _check_xlsx_zip_safety(file_bytes)

    # --- First pass with header=0 -----------------------------------------
    df = _read_dataframe(file_bytes, filename, header_row=0)
    # header_row_offset tracks which spreadsheet row contained the column headers.
    # Row 1 (1-based) = header_row=0. Row 2 (1-based) = header_row=1.
    # The first pandas data row (index 0) lives at absolute row = header_row_offset + 2.
    header_row_offset: int = 0  # header was row 1 (0-based index 0)

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
            header_row_offset = 1  # header was row 2 (0-based index 1)

    # --- Clean column names ---------------------------------------------------
    renamed: dict[Any, str | None] = {col: _clean_column_name(col) for col in df.columns}
    # Keep only columns whose cleaned name is non-empty
    good_cols = [orig for orig, clean in renamed.items() if clean]
    df = df[good_cols].copy()
    df.rename(columns={orig: renamed[orig] for orig in good_cols}, inplace=True)

    # --- Identify real rows BEFORE forward-fill -------------------------------
    # Excel files frequently have thousands of phantom rows beyond the last data
    # row. Their cells appear as NaN. ffill() would propagate real values into
    # them, making them look populated.  We mark rows with >= 2 non-null values
    # now (pre-ffill) as "real", then discard everything else after ffill runs.
    real_mask = df.notna().sum(axis=1) >= 2

    # --- Forward-fill (handles merged cells in Excel) -------------------------
    df.ffill(inplace=True)

    # --- Keep only rows that were real before ffill ---------------------------
    df = df[real_mask]

    # --- Row count guard ------------------------------------------------------
    if len(df) > MAX_ROWS:
        raise ValueError(
            f"File contains {len(df):,} data rows which exceeds the "
            f"{MAX_ROWS:,}-row limit. Split the file into smaller batches."
        )

    # --- Convert values -------------------------------------------------------
    rows: list[dict] = []
    for pandas_idx, row in df.iterrows():
        record = {col: _to_python(val) for col, val in row.items()}
        # Skip rows that are entirely None after conversion
        if all(v is None for v in record.values()):
            continue
        # Absolute Excel row number: pandas index is 0-based from the first data
        # row after the header. Add header_row_offset (0 or 1 for title skip),
        # +1 for the header row itself, +1 to convert from 0-based to 1-based,
        # then +1 more because pandas index 0 is the row immediately after header.
        # Formula: abs_row = pandas_idx + header_row_offset + 2
        record["_row_number"] = int(pandas_idx) + header_row_offset + 2
        rows.append(record)

    columns: list[str] = [k for k in (rows[0].keys() if rows else []) if k != "_row_number"]
    sample_rows: list[dict] = [
        {k: v for k, v in row.items() if k != "_row_number"} for row in rows[:5]
    ]

    logger.info("Parsed %d rows from '%s'", len(rows), filename)
    return {"rows": rows, "columns": columns, "sample_rows": sample_rows}
