"""RVTools-compliant .xlsx generator.

Produces a workbook with exactly 4 sheets in the order required by the IBM
Cool tool: vInfo, vNetwork, vPartition, vHost.
"""
from __future__ import annotations

import io
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side


# ---------------------------------------------------------------------------
# Header definitions — order and exact spelling must match the sample file.
# ---------------------------------------------------------------------------

VINFO_HEADERS = [
    "VM",
    "Powerstate",
    "Template",
    "CPUs",
    "Memory",
    "NICs",
    "Disks",
    "Provisioned MB",
    "In Use MB",
    "Datacenter",
    "Cluster",
    "Host",
    "OS according to the configuration file",
    "OS according to the VMware Tools",
]

VNETWORK_HEADERS = [
    "VM",
    "Powerstate",
    "Template",
    "SRM Placeholder",
    "NIC label",
    "Adapter",
    "Network",
    "Switch",
    "Connected",
    "Starts Connected",
    "Mac Address",
    "Type",
    "IPv4 Address",
    "IPv6 Address",
    "Direct Path IO",
    "Internal Sort Column",
    "Annotation",
]

VPARTITION_HEADERS = [
    "VM",
    "Powerstate",
    "Template",
    "Disk",
    "Capacity MB",
    "Consumed MB",
    "Free MB",
    "Free % ",   # trailing space is intentional — matches sample file exactly
    "Datacenter",
    "Cluster",
    "Host",
    "OS according to the configuration file",
    "OS according to the VMware Tools",
]

VHOST_HEADERS = [
    "Host",
    "Datacenter",
    "Cluster",
    "Config status",
    "CPU Model",
    "Speed",
    "HT Available",
    "HT Active",
    "# CPU",
    "Cores per CPU",
    "# Cores",
    "CPU usage %",
    "# Memory",
    "Memory usage %",
    "Console",
    "# NICs",
    "# HBAs",
    "# VMs",
    "VMs per Core",
    "# vCPUs",
    "vCPUs per Core",
    "vRAM",
    "VM Used memory",
    "VM Memory Swapped",
    "VM Memory Ballooned",
    "ESX Version",
    "Vendor",
    "Model",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_THIN = Side(style="thin")
_ALL_BORDERS = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)
_HEADER_FILL = PatternFill("solid", fgColor="D3D3D3")
_HEADER_FONT = Font(bold=True)


def _write_header(ws: Any, headers: list[str]) -> None:
    ws.append(headers)
    for cell in ws[1]:
        cell.font = _HEADER_FONT
        cell.fill = _HEADER_FILL
        cell.border = _ALL_BORDERS
        cell.alignment = Alignment(horizontal="center")


def _auto_size_columns(ws: Any, headers: list[str]) -> None:
    """Set column widths to content, capped at 50."""
    col_widths = [len(h) for h in headers]
    for row in ws.iter_rows(min_row=2, values_only=True):
        for i, val in enumerate(row):
            if val is not None:
                col_widths[i] = max(col_widths[i], len(str(val)))
    for i, width in enumerate(col_widths, start=1):
        ws.column_dimensions[ws.cell(1, i).column_letter].width = min(width + 2, 50)


def _get(d: dict, key: str, default: Any = None) -> Any:
    return d.get(key, default)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_rvtools_xlsx(records: list[dict], project_name: str) -> bytes:
    """Generate a standards-compliant RVTools .xlsx from normalized server records.

    Args:
        records: list of normalized_data dicts, each containing vinfo, vnetwork,
                 vpartition, and vhost keys.
        project_name: used for context (e.g., filename suggestion by caller).

    Returns:
        bytes: the complete Excel file ready to store or stream.
    """
    wb = Workbook()
    # Remove the default empty sheet created by openpyxl
    wb.remove(wb.active)

    ws_vinfo = wb.create_sheet("vInfo")
    ws_vnetwork = wb.create_sheet("vNetwork")
    ws_vpartition = wb.create_sheet("vPartition")
    ws_vhost = wb.create_sheet("vHost")

    _write_header(ws_vinfo, VINFO_HEADERS)
    _write_header(ws_vnetwork, VNETWORK_HEADERS)
    _write_header(ws_vpartition, VPARTITION_HEADERS)
    _write_header(ws_vhost, VHOST_HEADERS)

    seen_hosts: set[str] = set()

    for record in records:
        if record is None:
            continue

        vinfo = record.get("vinfo") or {}
        vnetwork_list = record.get("vnetwork") or []
        vpartition_list = record.get("vpartition") or []
        vhost = record.get("vhost") or {}

        # --- vInfo (one row per VM) ---
        if vinfo:
            ws_vinfo.append([
                _get(vinfo, "vm_name"),
                _get(vinfo, "powerstate"),
                _get(vinfo, "template"),
                _get(vinfo, "cpus"),
                _get(vinfo, "memory_mb"),
                _get(vinfo, "nics"),
                _get(vinfo, "disks"),
                _get(vinfo, "provisioned_mb"),
                _get(vinfo, "in_use_mb"),
                _get(vinfo, "datacenter"),
                _get(vinfo, "cluster"),
                _get(vinfo, "host"),
                _get(vinfo, "os_config"),
                _get(vinfo, "os_vmware_tools"),
            ])

        # --- vNetwork (one row per NIC) ---
        for nic in vnetwork_list:
            if nic is None:
                continue
            ws_vnetwork.append([
                _get(nic, "vm_name"),
                _get(nic, "powerstate"),
                _get(nic, "template"),
                _get(nic, "srm_placeholder"),
                _get(nic, "nic_label"),
                _get(nic, "adapter"),
                _get(nic, "network"),
                _get(nic, "switch"),
                _get(nic, "connected"),
                _get(nic, "starts_connected"),
                _get(nic, "mac_address"),
                _get(nic, "type"),
                _get(nic, "ipv4_address"),
                _get(nic, "ipv6_address"),
                _get(nic, "direct_path_io"),
                _get(nic, "internal_sort_column"),
                _get(nic, "annotation"),
            ])

        # --- vPartition (one row per disk/partition) ---
        for part in vpartition_list:
            if part is None:
                continue
            ws_vpartition.append([
                _get(part, "vm_name"),
                _get(part, "powerstate"),
                _get(part, "template"),
                _get(part, "disk_label"),
                _get(part, "capacity_mb"),
                _get(part, "consumed_mb"),
                _get(part, "free_mb"),
                _get(part, "free_pct"),
                _get(part, "datacenter"),
                _get(part, "cluster"),
                _get(part, "host"),
                _get(part, "os_config"),
                _get(part, "os_vmware_tools"),
            ])

        # --- vHost (deduplicated by host_name) ---
        if vhost:
            host_name = _get(vhost, "host_name") or ""
            if host_name and host_name not in seen_hosts:
                seen_hosts.add(host_name)
                ws_vhost.append([
                    _get(vhost, "host_name"),
                    _get(vhost, "datacenter"),
                    _get(vhost, "cluster"),
                    _get(vhost, "config_status"),
                    _get(vhost, "cpu_model"),
                    _get(vhost, "speed_mhz"),
                    _get(vhost, "ht_available"),
                    _get(vhost, "ht_active"),
                    _get(vhost, "num_cpu"),
                    _get(vhost, "cores_per_cpu"),
                    _get(vhost, "num_cores"),
                    _get(vhost, "cpu_usage_pct"),
                    _get(vhost, "memory_mb"),
                    _get(vhost, "memory_usage_pct"),
                    _get(vhost, "console"),
                    _get(vhost, "num_nics"),
                    _get(vhost, "num_hbas"),
                    _get(vhost, "num_vms"),
                    _get(vhost, "vms_per_core"),
                    _get(vhost, "num_vcpus"),
                    _get(vhost, "vcpus_per_core"),
                    _get(vhost, "vram_mb"),
                    _get(vhost, "vm_used_memory"),
                    _get(vhost, "vm_memory_swapped"),
                    _get(vhost, "vm_memory_ballooned"),
                    _get(vhost, "esx_version"),
                    _get(vhost, "vendor"),
                    _get(vhost, "model"),
                ])

    # Auto-size columns on all sheets
    _auto_size_columns(ws_vinfo, VINFO_HEADERS)
    _auto_size_columns(ws_vnetwork, VNETWORK_HEADERS)
    _auto_size_columns(ws_vpartition, VPARTITION_HEADERS)
    _auto_size_columns(ws_vhost, VHOST_HEADERS)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
