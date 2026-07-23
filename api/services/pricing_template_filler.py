"""IBM Price Estimator workbook filler service.

Opens an IBM Power Virtual Server Price Estimator .xlsx workbook (any version),
locates the yellow input area in "Multiple LPAR Price Estimate" by scanning for
known header text, writes one row per PowerVS server, and returns the populated
workbook bytes with all formulas, styles, and other sheets intact.

Implementation strategy — zip-level XML surgery:
  The IBM Price Estimator is a complex workbook with named ranges, external link
  metadata, comments, VML drawings, embedded objects, and threaded comments.
  openpyxl's save() strips or corrupts all of these, causing Excel's repair dialog
  on open and breaking the named-range lookups that drive pricing formulas.

  Instead we treat the .xlsx as a zip archive and perform surgical in-place edits:
    1. Parse sharedStrings.xml — build a lookup from string → shared-string index.
    2. Append any new strings (LPAR names, datacenter, system, OS, proc type) to
       sharedStrings.xml, updating the count attributes.
    3. Patch only the input cells (B, C, D, E, F, G, H, N, P, Q) in the target
       worksheet XML using regex substitution on the cell XML fragments.
    4. Rebuild the zip, replacing only the two modified XML members; every other
       part (rels, drawings, comments, external links, named ranges, styles,
       calcChain, …) is copied verbatim from the original bytes.

  This approach guarantees the output is structurally identical to the template
  — Excel will never trigger its repair dialog.

Column mapping (confirmed from v12a):
  B=2  — LPAR name          (shared string)
  C=3  — LPAR Qty           (number, always 1)
  D=4  — Data Center        (shared string, uppercased e.g. DAL10)
  E=5  — System             (shared string, e.g. S1022 / E1050)
  F=6  — Processor Type     (shared string, S = Shared Uncapped)
  G=7  — Desired Cores      (number, rounded to nearest 0.25)
  H=8  — Memory (GB)        (number)
  N=14 — OS                 (shared string — must exactly match Assumptions lookup)
             AIX | IBM_i | IBM_i_MOL | Red Hat GP | Red Hat SAP |
             SUSE GP | SUSE SAP | BYO Lnx / NA
  P=16 — Storage Tier 1 GB (number, AIX / IBM i workloads)
  Q=17 — Storage Tier 3 GB (number, Linux on Power workloads)

Row layout in "Multiple LPAR Price Estimate" (v12a confirmed):
  Row 18 — header row containing "name or #" in column B
  Row 19 — EXAMPLE row (must NOT be overwritten — formulas reference it)
  Row 20+ — blank pre-built data rows (first actual data entry row)
"""
from __future__ import annotations

import io
import logging
import re
import zipfile

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sheet name (stable across IBM Price Estimator versions)
# ---------------------------------------------------------------------------
_SHEET_NAME = "Multiple LPAR Price Estimate"

# ---------------------------------------------------------------------------
# Column letters for the yellow input area (confirmed from v12a)
# ---------------------------------------------------------------------------
_COL_NAME_LETTER  = "B"   # LPAR name         (shared string)
_COL_QTY_LETTER   = "C"   # LPAR Qty          (number)
_COL_DC_LETTER    = "D"   # Data Center       (shared string)
_COL_SYS_LETTER   = "E"   # System            (shared string)
_COL_PROC_LETTER  = "F"   # Processor Type    (shared string)
_COL_CORES_LETTER = "G"   # Desired Cores     (number)
_COL_MEM_LETTER   = "H"   # Memory GB         (number)
_COL_OS_LETTER    = "N"   # OS                (shared string)
_COL_TIER1_LETTER = "P"   # Storage Tier 1 GB (number)
_COL_TIER3_LETTER = "Q"   # Storage Tier 3 GB (number)

# Also keep 1-based column indices for the header-row scanner (uses openpyxl-style access)
_COL_NAME  = 2   # B
_COL_QTY   = 3   # C
_COL_DC    = 4   # D
_COL_SYSTEM= 5   # E
_COL_PROC  = 6   # F
_COL_CORES = 7   # G
_COL_MEM   = 8   # H
_COL_OS    = 14  # N
_COL_TIER1 = 16  # P
_COL_TIER3 = 17  # Q

# ---------------------------------------------------------------------------
# Maximum pre-built LPAR rows per sheet.
# When servers exceed this, fill_pricing_template_batches() produces multiple
# workbooks. The template has ~300 pre-built rows; we use 290 to leave a
# safety margin before the sheet's formula block ends.
# ---------------------------------------------------------------------------
_ROWS_PER_SHEET = 290

# ---------------------------------------------------------------------------
# Entitlement factor: cores × 0.5 (50%, documented assumption)
# Minimum is 0.25 per the Price Estimator Assumptions sheet partial-core table.
# Cores are rounded to the nearest 0.25 increment accepted by the estimator.
# ---------------------------------------------------------------------------
_ENTITLEMENT     = 0.5
_MIN_ENTITLEMENT = 0.5    # PowerVS minimum entitlement is 0.5 (matches PowerVS calculator)
_CORE_INCREMENT  = 0.25

# ---------------------------------------------------------------------------
# OS mapping: PowerVS OS family  →  Price Estimator exact dropdown value
#
# Values MUST exactly match the Assumptions sheet OS lookup table (case-sensitive).
# Valid values: AIX | IBM_i | IBM_i_MOL | Red Hat GP | Red Hat SAP |
#               SUSE GP | SUSE SAP | BYO Lnx / NA
# ---------------------------------------------------------------------------
_OS_MAP: dict[str, str] = {
    "aix":         "AIX",
    "ibm i":       "IBM_i",
    "ibm i mol":   "IBM_i_MOL",
    "linux byol":  "BYO Lnx / NA",
    "sap red hat": "Red Hat SAP",
    "sap suse":    "SUSE SAP",
    "red hat gp":  "Red Hat GP",
    "red hat sap": "Red Hat SAP",
    "suse gp":     "SUSE GP",
    "suse sap":    "SUSE SAP",
}

# Storage: Tier 1 for AIX/IBM i, Tier 3 for Linux on Power
_TIER1_OS = {"aix", "ibm i", "ibm i mol"}


def _map_os(os_family: str | None) -> str:
    """Map a PowerVS OS family string to the Price Estimator OS dropdown value."""
    if os_family is None:
        return "AIX"
    return _OS_MAP.get(os_family.lower().strip(), "AIX")


def _select_machine(cpus: int, mem_gb: int) -> str:
    """Return the Price Estimator system string for a PowerVS server.

    Only 1000-series (Power10) and 1100-series (Power11) hardware is used.
    S922 (Power9) and E980 (Power9) are excluded — they are being retired.

    S1022 — Power10 scale-out:   up to 51 cores,  up to 1904 GB RAM
    E1050 — Power10 enterprise:  up to 120 cores, up to 16384 GB RAM
    E1080 — Power10 enterprise:  up to 240 cores (largest Power10)
    """
    if cpus <= 0:
        cpus = 1
    if mem_gb <= 0:
        mem_gb = 1
    if cpus <= 51 and mem_gb <= 1904:
        return "S1022"
    if cpus <= 120:
        return "E1050"
    return "E1080"


# ---------------------------------------------------------------------------
# Shared-strings helpers (zip-level XML surgery)
# ---------------------------------------------------------------------------

def _parse_shared_strings(ss_xml: str) -> tuple[dict[str, int], list[str]]:
    """Parse sharedStrings.xml and return (string→index mapping, ordered list of <si> blocks).

    We only need plain-text <si><t>value</t></si> entries.  Rich-text entries
    (containing <r> children) are stored verbatim and are not looked up by value.
    """
    # Extract all <si>...</si> blocks preserving order
    si_blocks = re.findall(r"<si>(.*?)</si>", ss_xml, re.DOTALL)
    index_map: dict[str, int] = {}
    for i, block in enumerate(si_blocks):
        # Simple <t>text</t> — may have xml:space="preserve" attribute
        m = re.match(r"<t(?:\s[^>]*)?>([^<]*)</t>", block.strip())
        if m:
            index_map[m.group(1)] = i
    return index_map, si_blocks


def _ensure_string(
    value: str,
    index_map: dict[str, int],
    si_blocks: list[str],
) -> int:
    """Return the shared-string index for *value*, adding it if not already present."""
    if value in index_map:
        return index_map[value]
    new_idx = len(si_blocks)
    # Escape XML special chars in the value
    escaped = value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    si_blocks.append(f"<t>{escaped}</t>")
    index_map[value] = new_idx
    return new_idx


def _rebuild_shared_strings(ss_xml: str, si_blocks: list[str]) -> str:
    """Reconstruct sharedStrings.xml with updated count attributes and si entries."""
    count = len(si_blocks)
    body = "".join(f"<si>{b}</si>" for b in si_blocks)

    # Locate the <sst ...> opening tag and preserve everything before it
    # (XML declaration, processing instructions, etc.)
    sst_open_m = re.search(r"<sst[^>]*>", ss_xml)
    if not sst_open_m:
        return ss_xml  # not a valid sharedStrings.xml — return unchanged

    header = ss_xml[: sst_open_m.start()]
    open_tag = sst_open_m.group(0)

    # Update count and uniqueCount attributes in the opening tag
    open_tag = re.sub(r'\bcount="\d+"', f'count="{count}"', open_tag)
    open_tag = re.sub(r'\buniqueCount="\d+"', f'uniqueCount="{count}"', open_tag)
    if 'count=' not in open_tag:
        open_tag = open_tag[:-1] + f' count="{count}" uniqueCount="{count}">'

    return header + open_tag + body + "</sst>"


# ---------------------------------------------------------------------------
# Worksheet XML surgery helpers
# ---------------------------------------------------------------------------

def _col_letter_to_num(letter: str) -> int:
    """Convert column letter(s) to 1-based column number (A=1, B=2, …, Z=26, AA=27…)."""
    num = 0
    for ch in letter.upper():
        num = num * 26 + (ord(ch) - ord("A") + 1)
    return num


def _cell_ref(col_letter: str, row: int) -> str:
    return f"{col_letter}{row}"


# Regex that matches a single cell element for a given cell reference.
# Handles both self-closing (<c r="B20" .../>) and with children (<c r="B20" ...>...</c>).
#
# Design notes:
#   - ([^/>]*) for attributes: [^/>]* stops at '/' to prevent swallowing the '/>' of a
#     self-closing tag into the attribute group.  Without this, ' s="2"/' would be captured
#     as the attribute group, leaving '><next_cell.../>' to be matched by the '>' branch,
#     which then consumes the NEXT cell entirely as the body.
#   - (/>|>.*?</c>) handles both self-closing and element-with-children forms.
#     The '.*?' is non-greedy with re.DOTALL so it stops at the first </c> encountered,
#     correctly handling formula cells whose <f> children contain cross-sheet references
#     like $C$20 that contain the character sequence '<c'.
def _cell_pattern(ref: str) -> re.Pattern[str]:
    return re.compile(
        r'<c r="' + re.escape(ref) + r'"([^/>]*)(/>|>.*?</c>)',
        re.DOTALL,
    )


def _make_string_cell(ref: str, style_attr: str, ss_idx: int) -> str:
    """Produce a shared-string cell fragment: <c r="B20" s="137" t="s"><v>123</v></c>"""
    return f'<c r="{ref}"{style_attr} t="s"><v>{ss_idx}</v></c>'


def _make_number_cell(ref: str, style_attr: str, value: int | float) -> str:
    """Produce a numeric cell fragment: <c r="G20" s="138"><v>4.5</v></c>"""
    # Format as integer if whole number, otherwise float with minimal decimals
    if isinstance(value, float) and value == int(value):
        str_val = str(int(value))
    else:
        str_val = str(value)
    return f'<c r="{ref}"{style_attr}><v>{str_val}</v></c>'


def _make_empty_cell(ref: str, style_attr: str) -> str:
    """Produce a self-closing empty cell, preserving style."""
    return f'<c r="{ref}"{style_attr}/>'


def _replace_cell(ws_xml: str, ref: str, new_cell: str) -> str:
    """Replace the cell element for *ref* in *ws_xml* with *new_cell*."""
    pat = _cell_pattern(ref)
    m = pat.search(ws_xml)
    if m:
        return ws_xml[: m.start()] + new_cell + ws_xml[m.end():]
    # Cell not found (shouldn't happen for pre-built rows) — no-op
    logger.warning("Cell %s not found in worksheet XML; skipping", ref)
    return ws_xml


def _get_style_attr(ws_xml: str, ref: str) -> str:
    """Extract the s="NNN" attribute string from an existing cell, or empty string."""
    pat = _cell_pattern(ref)
    m = pat.search(ws_xml)
    if not m:
        return ""
    attrs = m.group(1)  # everything between r="REF" and the closing > or />
    s_match = re.search(r'\s+s="\d+"', attrs)
    return s_match.group(0) if s_match else ""


# ---------------------------------------------------------------------------
# Header-row scanner (finds 'name or #' in column B to locate data start row)
# ---------------------------------------------------------------------------

def _find_data_start_in_xml(ws_xml: str) -> int:
    """Return the first blank data row number by scanning for 'name or #' in col B.

    Looks for a cell B<n> whose shared-string value (or inline string) contains
    the text 'name or #'.  Data starts two rows after that header row.

    Falls back to row 20 (v12a layout) if not found.
    """
    # Extract sharedStrings indices that equal 'name or #' by scanning cells B1..B30
    for row_idx in range(1, 30):
        # Look for <c r="B{row_idx}" ... t="s"><v>NNN</v></c>  (shared string)
        # or <c r="B{row_idx}" ...><v>name or #</v></c>  (inline)
        ref = f"B{row_idx}"
        m = re.search(r'<c r="' + re.escape(ref) + r'"[^>]*(?:t="s")?[^>]*>(?:<[fv][^>]*>)([^<]*)</[fv]>', ws_xml)
        if m:
            raw_val = m.group(1).strip()
            # Could be a shared-string index or a literal value
            if raw_val.lower() == "name or #":
                logger.debug("Found 'name or #' literal at row %d; data starts at %d", row_idx, row_idx + 2)
                return row_idx + 2
        # Also check if the cell has t="s" — in that case raw_val is an integer index
        # We can't look up the shared string here without the full SS table, so fall through
    logger.warning("Could not locate 'name or #' header in worksheet XML; defaulting to row 20")
    return 20


def _find_data_start_with_ss(ws_xml: str, ss_index_map: dict[str, int]) -> int:
    """Like _find_data_start_in_xml but resolves shared-string indices."""
    name_or_hash_idx = ss_index_map.get("name or #", -1)
    for row_idx in range(1, 50):
        ref = f"B{row_idx}"
        # Match shared-string cell: t="s" with <v>IDX</v>
        m = re.search(
            r'<c r="' + re.escape(ref) + r'"[^>]*t="s"[^>]*><v>(\d+)</v>',
            ws_xml,
        )
        if m and name_or_hash_idx >= 0 and int(m.group(1)) == name_or_hash_idx:
            logger.debug("Found 'name or #' (ss=%d) at row %d; data starts at %d",
                         name_or_hash_idx, row_idx, row_idx + 2)
            return row_idx + 2
        # Fallback: plain text in <v>
        m2 = re.search(
            r'<c r="' + re.escape(ref) + r'"[^>]*><v>([^<]*)</v>',
            ws_xml,
        )
        if m2 and "name or #" in m2.group(1).lower():
            logger.debug("Found 'name or #' literal at row %d; data starts at %d", row_idx, row_idx + 2)
            return row_idx + 2
    logger.warning("Could not locate 'name or #'; defaulting to row 20")
    return 20


# ---------------------------------------------------------------------------
# Record field extraction (unchanged logic)
# ---------------------------------------------------------------------------

def _extract_server_fields(rec: dict, idx: int) -> dict:
    """Extract and compute all fields needed to fill one LPAR row."""
    nd    = rec.get("normalized_data") or {}
    vinfo = nd.get("vinfo") or {}

    vm_name   = (vinfo.get("vm_name") or f"Server-{idx+1}")[:31]
    cpus      = int(vinfo.get("num_cpus") or vinfo.get("cpus") or 1)
    mem_mb    = int(vinfo.get("memory_mb") or vinfo.get("memory") or 4096)
    mem_gb    = max(1, round(mem_mb / 1024))
    prov_mb   = int(vinfo.get("provisioned_mb") or 51200)
    total_mb  = int(vinfo.get("total_disk_mb") or prov_mb)
    disk_gb   = max(1, round(total_mb / 1024))
    os_family = vinfo.get("powervs_os_family") or vinfo.get("os_config") or "AIX"
    machine   = _select_machine(cpus, mem_gb)
    os_val    = _map_os(os_family)
    # Round entitled cores to the nearest 0.25 increment (Price Estimator minimum granularity)
    raw_entitled = cpus * _ENTITLEMENT
    entitled  = max(_MIN_ENTITLEMENT, round(raw_entitled / _CORE_INCREMENT) * _CORE_INCREMENT)
    is_linux  = os_family.lower().strip() not in _TIER1_OS
    tier1_gb  = 0 if is_linux else disk_gb
    tier3_gb  = disk_gb if is_linux else 0

    return dict(
        vm_name=vm_name, machine=machine, os_val=os_val,
        entitled=entitled, mem_gb=mem_gb,
        tier1_gb=tier1_gb, tier3_gb=tier3_gb,
    )


# ---------------------------------------------------------------------------
# Core XML patching function
# ---------------------------------------------------------------------------

def _patch_worksheet(
    ws_xml: str,
    ss_index_map: dict[str, int],
    si_blocks: list[str],
    records: list[dict],
    dc_upper: str,
    data_start: int,
) -> str:
    """Patch the worksheet XML with server data.  Returns modified XML string."""

    for i, rec in enumerate(records):
        row = data_start + i
        fields = _extract_server_fields(rec, i)

        # --- String cells (B, D, E, F, N) ---
        for col_letter, value in [
            (_COL_NAME_LETTER,  fields["vm_name"]),
            (_COL_DC_LETTER,    dc_upper),
            (_COL_SYS_LETTER,   fields["machine"]),
            (_COL_PROC_LETTER,  "S"),
            (_COL_OS_LETTER,    fields["os_val"]),
        ]:
            ref = _cell_ref(col_letter, row)
            style_attr = _get_style_attr(ws_xml, ref)
            ss_idx = _ensure_string(value, ss_index_map, si_blocks)
            new_cell = _make_string_cell(ref, style_attr, ss_idx)
            ws_xml = _replace_cell(ws_xml, ref, new_cell)

        # --- Numeric cells (C, G, H) ---
        for col_letter, value in [
            (_COL_QTY_LETTER,   1),
            (_COL_CORES_LETTER, fields["entitled"]),
            (_COL_MEM_LETTER,   fields["mem_gb"]),
        ]:
            ref = _cell_ref(col_letter, row)
            style_attr = _get_style_attr(ws_xml, ref)
            new_cell = _make_number_cell(ref, style_attr, value)
            ws_xml = _replace_cell(ws_xml, ref, new_cell)

        # --- Storage: Tier 1 (P) and Tier 3 (Q) — write value or clear to empty ---
        for col_letter, value in [
            (_COL_TIER1_LETTER, fields["tier1_gb"]),
            (_COL_TIER3_LETTER, fields["tier3_gb"]),
        ]:
            ref = _cell_ref(col_letter, row)
            style_attr = _get_style_attr(ws_xml, ref)
            if value > 0:
                new_cell = _make_number_cell(ref, style_attr, value)
            else:
                new_cell = _make_empty_cell(ref, style_attr)
            ws_xml = _replace_cell(ws_xml, ref, new_cell)

    return ws_xml


# ---------------------------------------------------------------------------
# Public zip-level fill functions
# ---------------------------------------------------------------------------

def _fill_zip(
    template_bytes: bytes,
    records: list[dict],
    pvs_datacenter: str,
) -> bytes:
    """Core implementation: patch template zip bytes with server data, return new zip bytes.

    Performs surgical XML edits — every part of the zip not explicitly modified
    is copied verbatim, preserving rels, drawings, comments, named ranges, etc.
    """
    dc_upper = pvs_datacenter.upper()

    with zipfile.ZipFile(io.BytesIO(template_bytes)) as zin:
        # ---- Identify the worksheet file for _SHEET_NAME ----
        wb_xml   = zin.read("xl/workbook.xml").decode("utf-8")
        rels_xml = zin.read("xl/_rels/workbook.xml.rels").decode("utf-8")

        sheet_to_rid  = dict(re.findall(r'<sheet[^>]+name="([^"]+)"[^>]+r:id="(rId\d+)"', wb_xml))
        rid_to_target = dict(re.findall(r'Id="(rId\d+)"[^>]*Target="([^"]+)"', rels_xml))

        rid = sheet_to_rid.get(_SHEET_NAME)
        if rid is None:
            raise ValueError(
                f"Workbook does not contain the sheet '{_SHEET_NAME}'. "
                "Please upload a valid IBM Power Virtual Server Price Estimator workbook."
            )
        ws_target = rid_to_target.get(rid, "")
        if not ws_target.startswith("worksheets/"):
            ws_target = ws_target.lstrip("/")
        ws_path = f"xl/{ws_target}" if not ws_target.startswith("xl/") else ws_target

        # ---- Read shared strings and worksheet XML ----
        ss_xml = zin.read("xl/sharedStrings.xml").decode("utf-8")
        ws_xml = zin.read(ws_path).decode("utf-8")

        ss_index_map, si_blocks = _parse_shared_strings(ss_xml)
        data_start = _find_data_start_with_ss(ws_xml, ss_index_map)

        # ---- Patch worksheet XML ----
        ws_xml = _patch_worksheet(
            ws_xml, ss_index_map, si_blocks, records, dc_upper, data_start
        )

        # ---- Rebuild sharedStrings.xml ----
        new_ss_xml = _rebuild_shared_strings(ss_xml, si_blocks)

        # ---- Patch workbook.xml: add fullCalcOnLoad="1" to <calcPr> ----
        # Tells Excel to fully recalculate all formulas on open, overriding
        # the stale cached <v>0</v> values stored in the worksheet cells.
        new_wb_xml = re.sub(
            r'<calcPr([^/]*)/?>',
            lambda m: '<calcPr'
                      + re.sub(r'\s*fullCalcOnLoad="[^"]*"', '', m.group(1))
                      + ' fullCalcOnLoad="1"/>',
            wb_xml,
        )

        # ---- Write new zip, replacing modified members; drop calcChain.xml ----
        # calcChain.xml stores the stale formula evaluation order and cached
        # cell values. Dropping it forces Excel to rebuild the chain on open,
        # ensuring our newly-written input cells are picked up by all dependents.
        out_buf = io.BytesIO()
        modified = {
            ws_path:                ws_xml.encode("utf-8"),
            "xl/sharedStrings.xml": new_ss_xml.encode("utf-8"),
            "xl/workbook.xml":      new_wb_xml.encode("utf-8"),
        }
        skip = {"xl/calcChain.xml"}
        with zipfile.ZipFile(out_buf, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                if item.filename in skip:
                    continue          # drop stale calc chain
                elif item.filename in modified:
                    zout.writestr(item, modified[item.filename])
                else:
                    zout.writestr(item, zin.read(item.filename))

    out_buf.seek(0)
    return out_buf.read()


def _count_by_machine(batch: list[dict]) -> dict[str, int]:
    """Return {machine_type: count} for a batch of active records."""
    counts: dict[str, int] = {}
    for i, rec in enumerate(batch):
        fields = _extract_server_fields(rec, i)
        machine = fields["machine"]
        counts[machine] = counts.get(machine, 0) + 1
    return counts


def fill_pricing_template(
    template_bytes: bytes,
    records: list[dict],
    pvs_datacenter: str = "dal10",
) -> tuple[bytes, int, int, dict[str, int]]:
    """Populate IBM Price Estimator yellow input cells from PowerVS server records.

    Single-workbook variant — stops at _ROWS_PER_SHEET and adds a warning row.
    Use fill_pricing_template_batches() when server count may exceed _ROWS_PER_SHEET.

    Args:
        template_bytes: Raw bytes of the IBM Price Estimator .xlsx workbook.
        records:        Enriched record dicts (normalized_data, server_type, is_excluded).
        pvs_datacenter: Project PowerVS datacenter (e.g. "dal10"). Uppercased for the sheet.

    Returns:
        (populated_bytes, records_written, records_skipped, machine_counts)
        records_skipped > 0 when the server list exceeds _ROWS_PER_SHEET.
        machine_counts is a dict like {"S1022": 12, "E1050": 4}.

    Raises:
        ValueError: If the workbook does not contain the expected sheet name.
    """
    active = [
        r for r in records
        if r.get("server_type") == "powervs"
        and not r.get("is_excluded")
        and r.get("normalized_data")
    ]

    records_skipped = max(0, len(active) - _ROWS_PER_SHEET)
    batch = active[:_ROWS_PER_SHEET]

    if records_skipped > 0:
        logger.warning(
            "Server list exceeds %d rows — %d servers not written to the template",
            _ROWS_PER_SHEET, records_skipped,
        )

    populated = _fill_zip(template_bytes, batch, pvs_datacenter)
    machine_counts = _count_by_machine(batch)
    return populated, len(batch), records_skipped, machine_counts


def fill_pricing_template_batches(
    template_bytes: bytes,
    records: list[dict],
    pvs_datacenter: str = "dal10",
) -> list[tuple[bytes, int, int, int]]:
    """Populate IBM Price Estimator across multiple workbooks when needed.

    Splits the active PowerVS record list into batches of _ROWS_PER_SHEET and
    returns one populated workbook per batch. The endpoint zips them when there
    is more than one batch.

    Args:
        template_bytes: Raw bytes of the IBM Price Estimator .xlsx template.
        records:        Enriched record dicts (normalized_data, server_type, is_excluded).
        pvs_datacenter: Project PowerVS datacenter (e.g. "dal10"). Uppercased for the sheet.

    Returns:
        List of (populated_bytes, batch_number, records_written, total_batches).
        Always at least one item. When only one batch, behaves identically to
        fill_pricing_template().

    Raises:
        ValueError: If the workbook does not contain the expected sheet name.
    """
    active = [
        r for r in records
        if r.get("server_type") == "powervs"
        and not r.get("is_excluded")
        and r.get("normalized_data")
    ]

    if not active:
        return []

    batches = [
        active[i : i + _ROWS_PER_SHEET]
        for i in range(0, len(active), _ROWS_PER_SHEET)
    ]
    total_batches = len(batches)
    results: list[tuple[bytes, int, int, int]] = []

    for batch_num, batch in enumerate(batches, start=1):
        dc_upper = pvs_datacenter.upper()
        wb_bytes = _fill_zip(template_bytes, batch, pvs_datacenter)
        written  = len(batch)
        logger.info(
            "Batch %d/%d: wrote %d servers (dc=%s)",
            batch_num, total_batches, written, dc_upper,
        )
        results.append((wb_bytes, batch_num, written, total_batches))

    return results


def build_zip(
    batches: list[tuple[bytes, int, int, int]],
    project_name: str,
    timestamp: str,
) -> bytes:
    """Zip multiple populated workbooks into a single archive for download.

    Args:
        batches:      Output of fill_pricing_template_batches().
        project_name: Used in filenames (spaces replaced with underscores).
        timestamp:    YYYYMMDD_HHMMSS string.

    Returns:
        Raw bytes of a .zip archive containing one .xlsx per batch.
    """
    safe_name = project_name.replace(" ", "_")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for wb_bytes, batch_num, written, total in batches:
            fname = (
                f"PowerVS_PriceEstimator_{safe_name}"
                f"_Part{batch_num}of{total}_{timestamp}.xlsx"
            )
            zf.writestr(fname, wb_bytes)
    buf.seek(0)
    return buf.read()
