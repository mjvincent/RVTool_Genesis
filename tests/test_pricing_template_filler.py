"""Tests for the IBM Price Estimator zip-surgery filler.

Builds a minimal but structurally valid .xlsx in-memory (as a raw zip) that
mirrors the column layout of the real IBM Price Estimator "Multiple LPAR
Price Estimate" sheet, then exercises every code path in
pricing_template_filler without needing the real (customer-data-bearing)
workbook.
"""
from __future__ import annotations

import io
import re
import zipfile

import pytest

from services.pricing_template_filler import (
    _ensure_string,
    _extract_server_fields,
    _find_data_start_with_ss,
    _map_os,
    _parse_shared_strings,
    _rebuild_shared_strings,
    _select_machine,
    fill_pricing_template,
    _ROWS_PER_SHEET,
)


# ---------------------------------------------------------------------------
# Helpers — build a minimal but valid IBM Price Estimator skeleton
# ---------------------------------------------------------------------------

_SHEET_NAME = "Multiple LPAR Price Estimate"

# Minimal workbook.xml — just enough to satisfy the zip-surgery parser
_WORKBOOK_XML = """\
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="Multiple LPAR Price Estimate" sheetId="1" r:id="rId1"/>
  </sheets>
  <calcPr calcId="191028"/>
</workbook>
"""

_WORKBOOK_RELS = """\
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" Target="sharedStrings.xml"/>
</Relationships>
"""

_CONTENT_TYPES = """\
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml"  ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>
</Types>
"""


def _build_shared_strings(*values: str) -> tuple[str, dict[str, int]]:
    """Build a minimal sharedStrings.xml containing the given values."""
    idx_map: dict[str, int] = {}
    si_parts: list[str] = []
    for i, v in enumerate(values):
        escaped = v.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        si_parts.append(f"<si><t>{escaped}</t></si>")
        idx_map[v] = i
    count = len(values)
    body = "".join(si_parts)
    xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        f'<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        f'count="{count}" uniqueCount="{count}">{body}</sst>'
    )
    return xml, idx_map


def _shared_string_cell(col: str, row: int, ss_idx: int, style: int = 1) -> str:
    return f'<c r="{col}{row}" s="{style}" t="s"><v>{ss_idx}</v></c>'


def _number_cell(col: str, row: int, value, style: int = 2) -> str:
    return f'<c r="{col}{row}" s="{style}"><v>{value}</v></c>'


def _empty_cell(col: str, row: int, style: int = 2) -> str:
    return f'<c r="{col}{row}" s="{style}"/>'


def _build_worksheet(
    ss_idx_name_or_hash: int,
    header_row: int = 18,
    data_rows: int = 300,
) -> str:
    """Build a worksheet XML that looks like the IBM estimator sheet.

    Row header_row has B = shared-string index for 'name or #'.
    Row header_row+1 is the EXAMPLE row (pre-filled with dummy data).
    Rows header_row+2 .. header_row+2+data_rows are blank pre-built data rows.
    """
    rows: list[str] = []

    # Header row — B cell is "name or #" as a shared string
    rows.append(
        f'<row r="{header_row}">'
        + _shared_string_cell("B", header_row, ss_idx_name_or_hash)
        + "</row>"
    )

    # EXAMPLE row (header_row + 1) — leave with dummy data, must NOT be overwritten
    example_row = header_row + 1
    rows.append(
        f'<row r="{example_row}">'
        + _shared_string_cell("B", example_row, 0)   # dummy LPAR name
        + _number_cell("C", example_row, 1)
        + _shared_string_cell("D", example_row, 0)
        + _shared_string_cell("E", example_row, 0)
        + _shared_string_cell("F", example_row, 0)
        + _number_cell("G", example_row, 1)
        + _number_cell("H", example_row, 16)
        + _shared_string_cell("N", example_row, 0)
        + _empty_cell("P", example_row)
        + _empty_cell("Q", example_row)
        + "</row>"
    )

    # Pre-built blank data rows
    data_start = header_row + 2
    for r in range(data_start, data_start + data_rows):
        rows.append(
            f'<row r="{r}">'
            + _empty_cell("B", r)
            + _empty_cell("C", r)
            + _empty_cell("D", r)
            + _empty_cell("E", r)
            + _empty_cell("F", r)
            + _empty_cell("G", r)
            + _empty_cell("H", r)
            + _empty_cell("N", r)
            + _empty_cell("P", r)
            + _empty_cell("Q", r)
            + "</row>"
        )

    sheet_data = "<sheetData>" + "".join(rows) + "</sheetData>"
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        + sheet_data
        + "</worksheet>"
    )


def _build_template(
    header_row: int = 18,
    data_rows: int = 300,
    extra_ss_values: list[str] | None = None,
) -> bytes:
    """Build a complete minimal IBM Price Estimator .xlsx (as raw zip bytes)."""
    base_strings = ["LPAR_EXAMPLE", "name or #"]
    if extra_ss_values:
        base_strings.extend(extra_ss_values)
    ss_xml, ss_idx = _build_shared_strings(*base_strings)
    name_or_hash_idx = ss_idx["name or #"]

    ws_xml = _build_worksheet(name_or_hash_idx, header_row=header_row, data_rows=data_rows)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", _CONTENT_TYPES)
        zf.writestr("xl/workbook.xml", _WORKBOOK_XML)
        zf.writestr("xl/_rels/workbook.xml.rels", _WORKBOOK_RELS)
        zf.writestr("xl/sharedStrings.xml", ss_xml)
        zf.writestr("xl/worksheets/sheet1.xml", ws_xml)
        # calcChain.xml — should be dropped by the filler
        zf.writestr("xl/calcChain.xml", "<calcChain/>")
    buf.seek(0)
    return buf.read()


def _make_record(
    name: str = "TESTSERVER01",
    cpus: int = 4,
    mem_mb: int = 16384,
    disk_mb: int = 102400,
    os_family: str = "AIX",
) -> dict:
    return {
        "server_type": "powervs",
        "is_excluded": False,
        "normalized_data": {
            "vinfo": {
                "vm_name": name,
                "num_cpus": cpus,
                "memory_mb": mem_mb,
                "provisioned_mb": disk_mb,
                "total_disk_mb": disk_mb,
                "powervs_os_family": os_family,
            }
        },
    }


def _read_filled(filled_bytes: bytes) -> tuple[str, str]:
    """Return (ws_xml, ss_xml) from a filled workbook."""
    with zipfile.ZipFile(io.BytesIO(filled_bytes)) as zf:
        ws_xml = zf.read("xl/worksheets/sheet1.xml").decode("utf-8")
        ss_xml = zf.read("xl/sharedStrings.xml").decode("utf-8")
    return ws_xml, ss_xml


def _get_cell_value(ws_xml: str, ss_xml: str, ref: str) -> str | int | float | None:
    """Return the value of a cell — resolves shared-string index to string."""
    # Try numeric cell first
    m_num = re.search(r'<c r="' + re.escape(ref) + r'"[^>]*><v>([^<]+)</v></c>', ws_xml)
    m_str = re.search(r'<c r="' + re.escape(ref) + r'"[^>]*t="s"[^>]*><v>(\d+)</v></c>', ws_xml)
    if m_str:
        idx = int(m_str.group(1))
        # Extract all <si> blocks
        si_blocks = re.findall(r"<si>(.*?)</si>", ss_xml, re.DOTALL)
        if idx < len(si_blocks):
            t_m = re.search(r"<t[^>]*>([^<]*)</t>", si_blocks[idx])
            return t_m.group(1) if t_m else None
        return None
    if m_num:
        val = m_num.group(1)
        try:
            return int(val) if "." not in val else float(val)
        except ValueError:
            return val
    return None


# ---------------------------------------------------------------------------
# Unit tests — individual helper functions
# ---------------------------------------------------------------------------

class TestMapOs:
    def test_aix(self):
        assert _map_os("AIX") == "AIX"

    def test_aix_lowercase(self):
        assert _map_os("aix") == "AIX"

    def test_ibm_i(self):
        assert _map_os("IBM i") == "IBM_i"

    def test_ibm_i_mol(self):
        assert _map_os("IBM i MOL") == "IBM_i_MOL"

    def test_linux_byol(self):
        assert _map_os("Linux BYOL") == "BYO Lnx / NA"

    def test_sap_red_hat(self):
        assert _map_os("SAP Red Hat") == "Red Hat SAP"

    def test_red_hat_gp(self):
        assert _map_os("Red Hat GP") == "Red Hat GP"

    def test_suse_gp(self):
        assert _map_os("SUSE GP") == "SUSE GP"

    def test_sap_suse(self):
        assert _map_os("SAP SUSE") == "SUSE SAP"

    def test_unknown_defaults_to_aix(self):
        assert _map_os("Windows Server 2019") == "AIX"

    def test_none_defaults_to_aix(self):
        assert _map_os(None) == "AIX"


class TestSelectMachine:
    def test_small_server_s1022(self):
        assert _select_machine(4, 64) == "S1022"

    def test_boundary_s1022_max_cores(self):
        assert _select_machine(51, 1904) == "S1022"

    def test_e1050_large_memory(self):
        # >1904 GB RAM forces E1050 even with few cores
        assert _select_machine(10, 2000) == "E1050"

    def test_e1050_many_cores(self):
        assert _select_machine(80, 512) == "E1050"

    def test_e1080_very_large(self):
        assert _select_machine(150, 2048) == "E1080"

    def test_zero_cpus_treated_as_one(self):
        assert _select_machine(0, 64) == "S1022"


class TestRebuildSharedStrings:
    def test_basic_round_trip(self):
        ss_xml, _ = _build_shared_strings("hello", "world")
        _, si_blocks = _parse_shared_strings(ss_xml)
        rebuilt = _rebuild_shared_strings(ss_xml, si_blocks)
        # Must contain the original strings
        assert "hello" in rebuilt
        assert "world" in rebuilt
        # count attributes must match
        assert 'count="2"' in rebuilt
        assert 'uniqueCount="2"' in rebuilt

    def test_new_string_appended(self):
        ss_xml, idx_map = _build_shared_strings("hello", "world")
        _, si_blocks = _parse_shared_strings(ss_xml)
        _ensure_string("newval", idx_map, si_blocks)
        rebuilt = _rebuild_shared_strings(ss_xml, si_blocks)
        assert "newval" in rebuilt
        assert 'count="3"' in rebuilt
        assert 'uniqueCount="3"' in rebuilt

    def test_no_duplicate_sst_tags(self):
        ss_xml, _ = _build_shared_strings("a", "b")
        _, si_blocks = _parse_shared_strings(ss_xml)
        rebuilt = _rebuild_shared_strings(ss_xml, si_blocks)
        # Only one <sst and one </sst>
        assert rebuilt.count("<sst") == 1
        assert rebuilt.count("</sst>") == 1

    def test_xml_declaration_preserved(self):
        ss_xml, _ = _build_shared_strings("x")
        _, si_blocks = _parse_shared_strings(ss_xml)
        rebuilt = _rebuild_shared_strings(ss_xml, si_blocks)
        assert rebuilt.startswith("<?xml")


class TestFindDataStart:
    def test_standard_header_row_18(self):
        ss_xml, idx_map = _build_shared_strings("LPAR_EXAMPLE", "name or #")
        ws_xml = _build_worksheet(idx_map["name or #"], header_row=18)
        assert _find_data_start_with_ss(ws_xml, idx_map) == 20

    def test_header_row_20(self):
        ss_xml, idx_map = _build_shared_strings("LPAR_EXAMPLE", "name or #")
        ws_xml = _build_worksheet(idx_map["name or #"], header_row=20)
        assert _find_data_start_with_ss(ws_xml, idx_map) == 22

    def test_missing_header_defaults_to_20(self):
        ss_xml, idx_map = _build_shared_strings("LPAR_EXAMPLE", "other text")
        ws_xml = _build_worksheet(0, header_row=18)  # ss idx 0 = "LPAR_EXAMPLE", not "name or #"
        result = _find_data_start_with_ss(ws_xml, idx_map)
        assert result == 20


# ---------------------------------------------------------------------------
# Integration tests — fill_pricing_template end-to-end
# ---------------------------------------------------------------------------

class TestFillPricingTemplate:
    def test_single_aix_record(self):
        template = _build_template()
        records = [_make_record("MYSERVER", cpus=8, mem_mb=65536, disk_mb=204800, os_family="AIX")]
        filled, written, skipped, _ = fill_pricing_template(template, records, pvs_datacenter="dal10")
        assert written == 1
        assert skipped == 0

        ws_xml, ss_xml = _read_filled(filled)

        # Row 20 (header=18, data_start=20)
        assert _get_cell_value(ws_xml, ss_xml, "B20") == "MYSERVER"
        assert _get_cell_value(ws_xml, ss_xml, "C20") == 1          # qty
        assert _get_cell_value(ws_xml, ss_xml, "D20") == "DAL10"    # datacenter uppercased
        assert _get_cell_value(ws_xml, ss_xml, "E20") == "S1022"    # 8 cpus, 64 GB → S1022
        assert _get_cell_value(ws_xml, ss_xml, "F20") == "S"        # proc type
        assert _get_cell_value(ws_xml, ss_xml, "G20") == 4.0        # 8 × 0.5 = 4.0 cores
        assert _get_cell_value(ws_xml, ss_xml, "H20") == 64         # 65536 MB / 1024
        assert _get_cell_value(ws_xml, ss_xml, "N20") == "AIX"
        # AIX → Tier 1, not Tier 3
        assert _get_cell_value(ws_xml, ss_xml, "Q20") is None or _get_cell_value(ws_xml, ss_xml, "Q20") == ""

    def test_linux_byol_uses_tier3(self):
        template = _build_template()
        records = [_make_record("LINUXBOX", cpus=4, mem_mb=16384, disk_mb=102400, os_family="Linux BYOL")]
        filled, written, _, _ = fill_pricing_template(template, records, pvs_datacenter="tok04")
        ws_xml, ss_xml = _read_filled(filled)

        assert _get_cell_value(ws_xml, ss_xml, "N20") == "BYO Lnx / NA"
        # Tier 3 should have the disk value; Tier 1 should be empty
        tier3 = _get_cell_value(ws_xml, ss_xml, "Q20")
        assert tier3 == 100  # 102400 / 1024 = 100 GB

    def test_datacenter_uppercased(self):
        template = _build_template()
        records = [_make_record()]
        filled, _, _, _ = fill_pricing_template(template, records, pvs_datacenter="lon06")
        ws_xml, ss_xml = _read_filled(filled)
        assert _get_cell_value(ws_xml, ss_xml, "D20") == "LON06"

    def test_minimum_entitlement_is_0_5(self):
        """Single-CPU server must get minimum 0.5 entitled cores, not 0.25."""
        template = _build_template()
        records = [_make_record(cpus=1)]
        filled, _, _, _ = fill_pricing_template(template, records)
        ws_xml, ss_xml = _read_filled(filled)
        assert _get_cell_value(ws_xml, ss_xml, "G20") == 0.5

    def test_multiple_records(self):
        template = _build_template()
        records = [
            _make_record(f"SRV-{i:03d}", cpus=4, mem_mb=16384, os_family="AIX")
            for i in range(10)
        ]
        filled, written, skipped, _ = fill_pricing_template(template, records)
        assert written == 10
        assert skipped == 0
        ws_xml, ss_xml = _read_filled(filled)
        # Verify first and last written row
        assert _get_cell_value(ws_xml, ss_xml, "B20") == "SRV-000"
        assert _get_cell_value(ws_xml, ss_xml, "B29") == "SRV-009"

    def test_example_row_not_overwritten(self):
        """Row 19 (the EXAMPLE row) must not be touched."""
        template = _build_template()
        # Fill 5 records starting at row 20 — row 19 should still have LPAR_EXAMPLE
        records = [_make_record(f"SRV-{i}", cpus=2) for i in range(5)]
        filled, _, _, _ = fill_pricing_template(template, records)
        ws_xml, ss_xml = _read_filled(filled)
        # The example row (19) should still have its original shared-string value (idx 0 = LPAR_EXAMPLE)
        example_val = _get_cell_value(ws_xml, ss_xml, "B19")
        assert example_val == "LPAR_EXAMPLE"

    def test_calcchain_dropped(self):
        """calcChain.xml must be removed from the output zip."""
        template = _build_template()
        records = [_make_record()]
        filled, _, _, _ = fill_pricing_template(template, records)
        with zipfile.ZipFile(io.BytesIO(filled)) as zf:
            assert "xl/calcChain.xml" not in zf.namelist()

    def test_full_calc_on_load_set(self):
        """workbook.xml must have fullCalcOnLoad=1 after fill."""
        template = _build_template()
        records = [_make_record()]
        filled, _, _, _ = fill_pricing_template(template, records)
        with zipfile.ZipFile(io.BytesIO(filled)) as zf:
            wb_xml = zf.read("xl/workbook.xml").decode("utf-8")
        assert 'fullCalcOnLoad="1"' in wb_xml

    def test_excluded_records_skipped(self):
        template = _build_template()
        records = [
            _make_record("INCLUDED"),
            {**_make_record("EXCLUDED"), "is_excluded": True},
        ]
        filled, written, _, _ = fill_pricing_template(template, records)
        assert written == 1
        ws_xml, ss_xml = _read_filled(filled)
        assert _get_cell_value(ws_xml, ss_xml, "B20") == "INCLUDED"

    def test_non_powervs_records_skipped(self):
        template = _build_template()
        records = [
            _make_record("PVS_SERVER"),
            {**_make_record("VPC_SERVER"), "server_type": "vm"},
        ]
        filled, written, _, _ = fill_pricing_template(template, records)
        assert written == 1

    def test_missing_sheet_raises_value_error(self):
        """Uploading a workbook without the expected sheet should raise ValueError."""
        # Build a workbook with a different sheet name
        buf = io.BytesIO()
        wb_xml = _WORKBOOK_XML.replace("Multiple LPAR Price Estimate", "Wrong Sheet Name")
        rels_xml = _WORKBOOK_RELS
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("[Content_Types].xml", _CONTENT_TYPES)
            zf.writestr("xl/workbook.xml", wb_xml)
            zf.writestr("xl/_rels/workbook.xml.rels", rels_xml)
            zf.writestr("xl/sharedStrings.xml", "<sst count='0' uniqueCount='0'></sst>")
            zf.writestr("xl/worksheets/sheet1.xml", "<worksheet><sheetData/></worksheet>")
        buf.seek(0)
        bad_template = buf.read()

        with pytest.raises(ValueError, match="Multiple LPAR Price Estimate"):
            fill_pricing_template(bad_template, [_make_record()])

    def test_e1050_machine_selection(self):
        """Server with >51 cores must get E1050."""
        template = _build_template()
        records = [_make_record(cpus=80, mem_mb=524288)]  # 512 GB RAM
        filled, _, _, _ = fill_pricing_template(template, records)
        ws_xml, ss_xml = _read_filled(filled)
        assert _get_cell_value(ws_xml, ss_xml, "E20") == "E1050"

    def test_e1080_machine_selection(self):
        """Server with >120 cores must get E1080."""
        template = _build_template()
        records = [_make_record(cpus=150, mem_mb=1048576)]  # 1 TB RAM
        filled, _, _, _ = fill_pricing_template(template, records)
        ws_xml, ss_xml = _read_filled(filled)
        assert _get_cell_value(ws_xml, ss_xml, "E20") == "E1080"
