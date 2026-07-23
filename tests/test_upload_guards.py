"""Unit tests: upload safety guards in spreadsheet_parser.

Covers:
- ZIP decompression-ratio rejection (zip bomb simulation)
- Total uncompressed-size rejection
- Row-count ceiling rejection
- Clean small file passes all guards
"""
from __future__ import annotations

import io
import zipfile

import openpyxl
import pytest

from services.spreadsheet_parser import (
    MAX_DECOMPRESSION_RATIO,
    MAX_ROWS,
    MAX_UNCOMPRESSED_BYTES,
    _check_xlsx_zip_safety,
    parse_spreadsheet,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_xlsx_bytes(num_rows: int = 5, columns: list[str] | None = None) -> bytes:
    """Build a minimal valid XLSX workbook with the given number of data rows."""
    if columns is None:
        columns = ["VM Name", "CPU", "RAM (MB)", "OS"]
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(columns)
    for i in range(num_rows):
        ws.append([f"server-{i:05d}", 4, 8192, "RHEL 8"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _make_zip_bomb_bytes(ratio: int = MAX_DECOMPRESSION_RATIO + 10) -> bytes:
    """Craft an XLSX-shaped ZIP where one member has an artificially large
    uncompressed-size header (simulates a zip-bomb declaration without actually
    allocating the memory)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        # A real XLSX requires at minimum [Content_Types].xml to be a valid ZIP.
        # We write a tiny compressed payload but lie about the uncompressed size
        # by constructing a raw ZipInfo with inflated file_size.
        small_data = b"x" * 512  # 512 bytes of actual content
        info = zipfile.ZipInfo("xl/worksheets/sheet1.xml")
        info.compress_type = zipfile.ZIP_STORED  # store uncompressed so ratio = 1
        zf.writestr(info, small_data)

        # Second member: genuinely compressible to manufacture a high ratio.
        # Write 8 KB of repeated bytes (compresses to ~20 bytes with deflate).
        repetitive = b"A" * 8192
        zf.writestr("xl/sharedStrings.xml", repetitive)

    return buf.getvalue()


def _make_oversized_zip_bytes() -> bytes:
    """Craft an XLSX ZIP whose total declared uncompressed size exceeds the limit.

    We manipulate the ZipInfo.file_size field to fake a huge entry without
    allocating memory. zipfile reads this from the central directory header.
    """
    buf = io.BytesIO()
    # Build a valid ZIP first
    with zipfile.ZipFile(buf, mode="w") as zf:
        zf.writestr("[Content_Types].xml", "<Types/>")
    raw = bytearray(buf.getvalue())

    # Locate the central directory and patch the uncompressed size fields.
    # This is a low-level simulation; for our guard test we instead build a ZIP
    # with many entries whose declared sizes sum past the threshold.
    return raw  # returned as-is for the size-sum path tested differently below


# ---------------------------------------------------------------------------
# _check_xlsx_zip_safety — decompression ratio
# ---------------------------------------------------------------------------

def test_zip_safety_passes_for_normal_xlsx():
    """A legitimately compressed XLSX should pass the safety check without error."""
    xlsx_bytes = _make_xlsx_bytes(num_rows=10)
    # Should not raise
    _check_xlsx_zip_safety(xlsx_bytes)


def test_zip_safety_high_ratio_rejected():
    """A ZIP member with a decompression ratio over the limit must be rejected."""
    # Build a XLSX with a highly compressible member (all identical bytes).
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        # 1 MB of 'A' compresses to ~1 KB — ratio ~1000×
        zf.writestr("xl/sharedStrings.xml", b"A" * (1024 * 1024))
        zf.writestr("[Content_Types].xml", b"<Types/>")
    zip_bytes = buf.getvalue()

    with pytest.raises(ValueError, match="decompression ratio"):
        _check_xlsx_zip_safety(zip_bytes)


def test_zip_safety_total_size_rejected():
    """If total declared uncompressed bytes exceed MAX_UNCOMPRESSED_BYTES, reject.

    Uses ZIP_STORED (uncompressed) entries so the decompression-ratio check
    (which only fires for compressed_size >= 1 KB) stays below the ratio limit
    and the total-size accumulator is what triggers the rejection.
    """
    limit = MAX_UNCOMPRESSED_BYTES
    # Use 64 MB STORED entries; ratio = 1× so the ratio guard won't fire.
    chunk = 64 * 1024 * 1024
    members_needed = (limit // chunk) + 2  # enough to breach the total limit

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w") as zf:
        for i in range(members_needed):
            info = zipfile.ZipInfo(f"xl/sheet{i}.xml")
            info.compress_type = zipfile.ZIP_STORED
            # Write a small placeholder — ZipInfo.file_size is set from actual data
            # on write, so we write the real chunk size to trigger the accumulator.
            zf.writestr(info, b"A" * chunk)
    zip_bytes = buf.getvalue()

    with pytest.raises(ValueError, match="uncompressed content exceeds"):
        _check_xlsx_zip_safety(zip_bytes)


# ---------------------------------------------------------------------------
# parse_spreadsheet — row-count guard
# ---------------------------------------------------------------------------

def test_row_count_below_limit_passes():
    """A file with fewer than MAX_ROWS rows must parse successfully."""
    xlsx_bytes = _make_xlsx_bytes(num_rows=100)
    result = parse_spreadsheet(xlsx_bytes, "test.xlsx")
    assert len(result["rows"]) == 100


def test_row_count_at_limit_passes():
    """A file with exactly MAX_ROWS rows must parse successfully."""
    xlsx_bytes = _make_xlsx_bytes(num_rows=MAX_ROWS)
    result = parse_spreadsheet(xlsx_bytes, "test.xlsx")
    assert len(result["rows"]) == MAX_ROWS


def test_row_count_over_limit_rejected():
    """A file with more than MAX_ROWS rows must raise ValueError."""
    xlsx_bytes = _make_xlsx_bytes(num_rows=MAX_ROWS + 1)
    with pytest.raises(ValueError, match=f"{MAX_ROWS + 1:,}.*row"):
        parse_spreadsheet(xlsx_bytes, "test.xlsx")


# ---------------------------------------------------------------------------
# parse_spreadsheet — zip-bomb path (end-to-end via parse_spreadsheet)
# ---------------------------------------------------------------------------

def test_parse_spreadsheet_rejects_zip_bomb():
    """parse_spreadsheet must raise ValueError before pandas touches a zip-bomb XLSX."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("xl/sharedStrings.xml", b"A" * (1024 * 1024))
        zf.writestr("[Content_Types].xml", b"<Types/>")
    zip_bytes = buf.getvalue()

    with pytest.raises(ValueError, match="decompression ratio|zip bomb"):
        parse_spreadsheet(zip_bytes, "crafted.xlsx")
