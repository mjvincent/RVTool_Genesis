"""AI normalizer — calls Ollama to map raw server data to the RVTools schema.

Strategy: Ask the LLM only for the fields it can meaningfully derive from customer data
(vinfo, vnetwork, vpartition, server_type, and assumptions). The vHost record is
synthesized entirely in Python from sensible IBM defaults — it is always a set of
standard assumptions, so asking the LLM to invent 28 fields wastes context budget and
causes truncation errors.
"""
from __future__ import annotations

import json
import logging
import re

import httpx

from core.config import settings
from services.network_inference import get_network_assumptions

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# vHost synthesis (pure Python — no LLM needed)
# ---------------------------------------------------------------------------

def _synthesize_vhost(vm_name: str, datacenter: str, cluster: str, memory_mb: int, cpus: int) -> tuple[dict, list[dict]]:
    """Build a representative ESXi vHost record from IBM defaults.

    Returns (vhost_dict, assumptions_list).
    All fields are documented as low-confidence assumptions.
    """
    host_name = f"{vm_name}-host.customer.com"
    host_memory_mb = max(int(memory_mb * 1.2), 1)  # 20% overhead, min 1 to avoid div/0
    memory_usage_pct = round((memory_mb / host_memory_mb) * 100, 1) if host_memory_mb > 0 else 0.0
    vcpus_per_core = round(cpus / 16, 1)

    vhost = {
        "host_name": host_name,
        "datacenter": datacenter,
        "cluster": cluster,
        "config_status": "Normal",
        "cpu_model": "Intel(R) Xeon(R) CPU E5-2680 0 @ 2.70GHz",
        "speed_mhz": 2700,
        "ht_available": "True",
        "ht_active": "True",
        "num_cpu": 2,
        "cores_per_cpu": 8,
        "num_cores": 16,
        "cpu_usage_pct": 25.0,
        "memory_mb": host_memory_mb,
        "memory_usage_pct": memory_usage_pct,
        "console": "False",
        "num_nics": 4,
        "num_hbas": 2,
        "num_vms": 1,
        "vms_per_core": round(1 / 16, 3),
        "num_vcpus": cpus,
        "vcpus_per_core": vcpus_per_core,
        "vram_mb": memory_mb,
        "vm_used_memory": 0,
        "vm_memory_swapped": 0,
        "vm_memory_ballooned": 0,
        "esx_version": "VMware ESXi 7.0.0 build-default",
        "vendor": "IBM",
        "model": "IBM Power Systems",
    }

    assumptions = [
        {"field_name": "vHost/host_name", "assumed_value": host_name, "original_value": None,
         "reasoning": "Synthesized from VM name — no physical host data provided", "confidence": "low"},
        {"field_name": "vHost/cpu_model", "assumed_value": "Intel(R) Xeon(R) CPU E5-2680 0 @ 2.70GHz", "original_value": None,
         "reasoning": "IBM standard host CPU model default", "confidence": "low"},
        {"field_name": "vHost/memory_mb", "assumed_value": str(host_memory_mb), "original_value": None,
         "reasoning": f"VM memory ({memory_mb} MB) + 20% host overhead", "confidence": "low"},
        {"field_name": "vHost/esx_version", "assumed_value": "VMware ESXi 7.0.0 build-default", "original_value": None,
         "reasoning": "IBM standard ESX version default", "confidence": "low"},
        {"field_name": "vHost/vendor+model", "assumed_value": "IBM / IBM Power Systems", "original_value": None,
         "reasoning": "IBM infrastructure default", "confidence": "low"},
    ]

    return vhost, assumptions


# ---------------------------------------------------------------------------
# PowerVS OS detection — AIX, IBM i, and Linux-on-Power → PowerVS designation
# ---------------------------------------------------------------------------

# Simple substring patterns (fast path for the most common cases).
_POWERVS_OS_SIMPLE = ["aix", "ibm i", "ibmi", "i/os", "os/400", "ibm os/400",
                      "linux byol", "linux on power", "power linux",
                      "sap red hat", "sap redhat", "red hat gp",
                      "sap suse", "sap sles", "suse gp"]

# Regex patterns for variants that need flexible matching.
_POWERVS_OS_REGEX: list[re.Pattern[str]] = [
    re.compile(r"rhel.*power",          re.IGNORECASE),
    re.compile(r"red\s*hat.*power",     re.IGNORECASE),
    re.compile(r"red\s*hat\s*gp",       re.IGNORECASE),
    re.compile(r"sap\s*red\s*hat",      re.IGNORECASE),
    re.compile(r"sap\s*redhat",         re.IGNORECASE),
    re.compile(r"sap\s*suse",           re.IGNORECASE),
    re.compile(r"sap\s*sles",           re.IGNORECASE),
    re.compile(r"suse.*power",          re.IGNORECASE),
    re.compile(r"suse\s*gp",            re.IGNORECASE),
    re.compile(r"sles.*power",          re.IGNORECASE),
    re.compile(r"linux\s*byol",         re.IGNORECASE),
    re.compile(r"linux\s*on\s*power",   re.IGNORECASE),
    re.compile(r"power\s*linux",        re.IGNORECASE),
    re.compile(r"sap\s*hana",           re.IGNORECASE),
]


def _is_powervs_os(os_str: str) -> bool:
    """Return True if the OS string indicates an AIX, IBM i, or Linux-on-Power workload.

    Covers all 8 IBM Cool PowerVS OS families:
    AIX | IBM i | IBM i MOL | Linux BYOL | SAP SUSE | SAP Red Hat | Red Hat GP | SUSE GP
    """
    lower = os_str.lower()
    if any(pat in lower for pat in _POWERVS_OS_SIMPLE):
        return True
    return any(pat.search(os_str) for pat in _POWERVS_OS_REGEX)


# ---------------------------------------------------------------------------
# PowerVS OS family mapper — maps OS strings to the 8 IBM Cool PowerVS families
# ---------------------------------------------------------------------------

# Ordered patterns — first match wins.  More specific entries come before general ones.
_POWERVS_FAMILY_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # IBM i MOL (must precede generic IBM i)
    (re.compile(r"ibm\s*i\s*mol|i\s*mol",                          re.IGNORECASE), "IBM i MOL"),
    # IBM i
    (re.compile(r"ibm\s*i\b|ibmi\b|i/os|os/400",                   re.IGNORECASE), "IBM i"),
    # SAP Red Hat (must precede generic Red Hat GP)
    (re.compile(r"sap\s*red\s*hat|sap\s*redhat|red\s*hat.*sap|rhel.*sap|sap\s*hana",
                re.IGNORECASE), "SAP Red Hat"),
    # SAP SUSE (must precede generic SUSE GP)
    (re.compile(r"sap\s*suse|sap\s*sles|suse.*sap|sles.*sap",      re.IGNORECASE), "SAP SUSE"),
    # Red Hat GP
    (re.compile(r"red\s*hat.*power|rhel.*power|red\s*hat\s*gp",    re.IGNORECASE), "Red Hat GP"),
    # SUSE GP
    (re.compile(r"suse.*power|sles.*power|suse\s*gp",              re.IGNORECASE), "SUSE GP"),
    # AIX (any version)
    (re.compile(r"\baix\b",                                         re.IGNORECASE), "AIX"),
    # Linux BYOL — any other Linux on Power
    (re.compile(r"linux|rhel|suse|sles|ubuntu|debian|centos|rocky|alma",
                re.IGNORECASE), "Linux BYOL"),
]


def _map_powervs_os_family(os_config: str) -> str:
    """Map a normalised OS string to one of the 8 IBM Cool PowerVS OS family strings.

    IBM Cool PowerVS families:
      AIX | IBM i | IBM i MOL | Linux BYOL | SAP SUSE | SAP Red Hat | Red Hat GP | SUSE GP

    Returns "AIX" as the fallback for unrecognised PowerVS records (AIX is the most
    common PowerVS workload type and is the safest pricing default).
    """
    for pattern, family in _POWERVS_FAMILY_PATTERNS:
        if pattern.search(os_config):
            return family
    return "AIX"


_POWERVS_ASSUMPTION = {
    "field_name": "server_type",
    "assumed_value": "powervs",
    "original_value": None,
    "reasoning": (
        "Operating system is AIX, IBM i, or Linux-on-Power — automatically designated "
        "as an IBM Power Virtual Server (PowerVS) workload. These workloads require a "
        "separate IBM Cool pricing exercise from x86/VPC workloads."
    ),
    "confidence": "high",
}


# ---------------------------------------------------------------------------
# LLM Prompt — focused only on fields the LLM can derive
# ---------------------------------------------------------------------------

# Compact prompt — stripped to minimum tokens. Assumptions are generated in Python.
# Each line kept short to reduce both prompt tokens and output tokens.
_SYSTEM_PROMPT = (
    "Convert this server row to IBM RVTools JSON. "
    "Return ONLY valid JSON starting with { and ending with }. "
    "No markdown, no text outside the JSON.\n\n"
    "CRITICAL RULES:\n"
    "1. vm_name = the server/hostname from the data. NEVER append -host.customer.com to vm_name.\n"
    "2. memory_mb = RAM in megabytes as an INTEGER. If the source value is in GB, multiply by 1024. Example: 64 GB = 65536 MB.\n"
    "3. template = the string \"FALSE\" (not a boolean).\n"
    "4. connected/starts_connected/direct_path_io/srm_placeholder = the string \"True\" or \"False\" (not booleans).\n"
    "5. nics = integer count of network adapters, default 1 if unknown.\n"
    "6. disks = integer count of disks, default 1 if unknown.\n"
    "7. os_vmware_tools = same full OS string as os_config (e.g. 'Microsoft Windows Server 2019 (64-bit)'), NOT 'toolsOk'.\n"
    "8. capacity_mb and consumed_mb = integers in MB. If source is GB, multiply by 1024.\n"
    "9. server_type = 'powervs' when OS is AIX, IBM i, or any Linux-on-Power variant (SAP Red Hat, SAP SUSE, Red Hat GP, SUSE GP, Linux BYOL). Use 'vm' or 'bare_metal' for all other OS types.\n\n"
    "Required fields:\n"
    '{"server_type":"vm|bare_metal|powervs (use powervs for AIX, IBM i, or Linux-on-Power OS)",'
    '"vinfo":{"vm_name":str,"powerstate":"poweredOn|poweredOff","template":"FALSE",'
    '"cpus":int,"memory_mb":int(RAM in MB - multiply GB by 1024),"nics":int(default 1),"disks":int(default 1),'
    '"provisioned_mb":int(total disk MB),"in_use_mb":int(default provisioned_mb*0.6),'
    '"datacenter":str(default "Datacenter1"),"cluster":str(default "Cluster1"),'
    '"host":str(vm_name+"-host.customer.com"),'
    '"os_config":str(full OS name e.g. "Microsoft Windows Server 2019 (64-bit)"),'
    '"os_vmware_tools":str(same full OS name as os_config)},'
    '"vnetwork":[{"vm_name":str,"powerstate":"poweredOn","template":"FALSE",'
    '"srm_placeholder":"False","nic_label":"Network adapter 1",'
    '"adapter":"Vmxnet3","network":"VM Network","switch":"vSwitch0",'
    '"connected":"True","starts_connected":"True","mac_address":"00:50:56:00:00:01",'
    '"type":"VirtualVmxnet3","ipv4_address":str(or "10.0.1.2"),'
    '"ipv6_address":"","direct_path_io":"False","internal_sort_column":0,"annotation":""}],'
    '"vpartition":[{"vm_name":str,"powerstate":"poweredOn","template":"FALSE",'
    '"disk_label":"C:\\\\ for Windows or / for Linux","capacity_mb":int(disk size in MB),'
    '"consumed_mb":int(default capacity_mb*0.6),'
    '"free_mb":int(capacity_mb-consumed_mb),"free_pct":float(free_mb/capacity_mb*100),'
    '"datacenter":str,"cluster":str,"host":str,"os_config":str,"os_vmware_tools":str}],'
    '"assumptions":[]}'
    "\n\nRemember: ALL memory and disk values MUST be integers in MB. GB * 1024 = MB.\n\n"
)


# Known column mappings for spreadsheets with Unnamed columns
# (detected from the Cognizant OmniCare RFP spreadsheet structure)
_UNNAMED_COL_MAP = {
    "Unnamed: 0":  "server_name",
    "Unnamed: 1":  "notes",
    "Unnamed: 2":  "environment",
    "Unnamed: 3":  "os",
    "Unnamed: 4":  "application",
    "Unnamed: 5":  "vcpus",
    "Unnamed: 6":  "cpu_speed_or_ram_gb",
    "Unnamed: 7":  "disk_gb",
    "Unnamed: 8":  "ram_mb_or_disk_mb",
    "Unnamed: 9":  "pool_or_cluster_name",
    "Unnamed: 10": "ha_enabled",
    "Unnamed: 11": "extra_1",
    "Unnamed: 12": "storage_notes",
    "Unnamed: 13": "added_notes",
    "Unnamed: 14": "utilization_ratio",
    "Grouped cells are paired clusters": "cluster_type",
}


def _rename_unnamed_columns(raw_data: dict) -> dict:
    """Rename 'Unnamed: N' keys to meaningful names so the LLM understands them."""
    unnamed_count = sum(1 for k in raw_data if str(k).startswith("Unnamed:"))
    if unnamed_count == 0:
        return raw_data
    return {_UNNAMED_COL_MAP.get(k, k): v for k, v in raw_data.items()}


def _build_prompt(raw_data: dict) -> str:
    # Rename unnamed columns, strip nulls/blanks, truncate long string values
    renamed = _rename_unnamed_columns(raw_data)
    trimmed = {}
    for k, v in renamed.items():
        if v is None:
            continue
        sv = str(v).strip()
        if sv in ("", "nan", "NaN", "None"):
            continue
        # Truncate any value longer than 80 chars to avoid bloating the prompt
        if len(sv) > 80:
            sv = sv[:77] + "..."
            v = sv
        trimmed[k] = v
    return (
        _SYSTEM_PROMPT
        + f"Server row: {json.dumps(trimmed, default=str)}\n\nJSON:"
    )


def _strip_markdown_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```\s*$", "", text)
    return text.strip()


def _sanitize_llm_text(text: str) -> str:
    """Fix common LLM output quirks before JSON parsing.

    - Replace Python booleans (True/False/None) with JSON equivalents
    - Evaluate simple inline arithmetic expressions like  8192 * 1024
      and replace them with the integer result (handles // comments too)
    - Strip C-style // line comments inside JSON strings
    """
    # Python bool/null → JSON
    text = re.sub(r'\bTrue\b',  'true',  text)
    text = re.sub(r'\bFalse\b', 'false', text)
    text = re.sub(r'\bNone\b',  'null',  text)

    # Evaluate arithmetic expressions like:
    #   8192 * 1024, // GB to MB
    #   0.6 * 7737
    #   (225653555) / (564133888) * 100
    def _eval_arith(m: re.Match) -> str:
        expr = m.group(0).strip()
        # Strip trailing // comment
        expr = re.sub(r'//[^\n]*$', '', expr).strip().rstrip(',')
        # Allow only digits, whitespace, basic operators, parens, dots
        if re.fullmatch(r'[\d\s\+\-\*\/\.\(\)]+', expr):
            try:
                result = float(eval(expr))  # nosec — safe pattern
                # Return int if it's a whole number, else 1-decimal float
                return str(int(result)) if result == int(result) else str(round(result, 1))
            except Exception:
                pass
        return m.group(0)

    # Match arithmetic expressions including parenthesized forms, with optional // comment
    text = re.sub(
        r'[\d\s\(\)]*(?:[\d.]+|\([\d.]+\))\s*(?:[+\-*/]\s*(?:[\d.]+|\([\d.]+\))\s*)+(?://[^\n",}\]]*)?',
        _eval_arith,
        text,
    )

    # Strip remaining // line comments
    text = re.sub(r'//[^\n"]*', '', text)

    return text


def _extract_json(text: str) -> str:
    """Extract the first complete JSON object from the response text.

    Local LLMs sometimes emit a short preamble before the JSON object,
    or truncate mid-object (no closing brace). Both cases are handled.
    """
    text = _strip_markdown_fences(text)
    text = _sanitize_llm_text(text)
    start = text.find("{")
    if start == -1:
        return text
    end = text.rfind("}")
    if end == -1 or end < start:
        # Truncated — return from first { to the end so _repair_truncated_json can fix it
        return text[start:]
    return text[start : end + 1]


# ---------------------------------------------------------------------------
# OS name normalization
# ---------------------------------------------------------------------------

# Maps common shorthand → IBM-standard full OS name (used by VMware/IBM Cool)
_OS_NORMALIZATION: list[tuple[str, str]] = [
    # ── x86 VPC SAP/SQL variants — must come BEFORE generic RHEL/SUSE/Windows entries ──
    # RHEL for SAP (x86 VPC)
    (r"red\s*hat.*for.*sap",              "Red Hat Enterprise Linux for SAP (64-bit)"),
    (r"rhel.*for.*sap",                   "Red Hat Enterprise Linux for SAP (64-bit)"),
    (r"rhel.*sap(?!.*power)",             "Red Hat Enterprise Linux for SAP (64-bit)"),
    # SUSE for SAP (x86 VPC) — negative lookahead excludes Power variants
    (r"suse.*for.*sap",                   "SUSE Linux Enterprise Server for SAP (64-bit)"),
    (r"sles.*for.*sap",                   "SUSE Linux Enterprise Server for SAP (64-bit)"),
    (r"sles.*sap(?!.*power)",             "SUSE Linux Enterprise Server for SAP (64-bit)"),
    # Windows with SQL Server
    (r"windows.*sql\s*server",            "Microsoft Windows Server with SQL Server (64-bit)"),
    (r"windows.*sql(?!.*power)",          "Microsoft Windows Server with SQL Server (64-bit)"),
    (r"sql\s*server.*windows",            "Microsoft Windows Server with SQL Server (64-bit)"),

    # ── Red Hat Enterprise Linux ──────────────────────────────────────────────
    (r"rhel\s*9",                         "Red Hat Enterprise Linux 9 (64-bit)"),
    (r"rhel\s*8",                         "Red Hat Enterprise Linux 8 (64-bit)"),
    (r"rhel\s*7",                         "Red Hat Enterprise Linux 7 (64-bit)"),
    (r"rhel\s*6",                         "Red Hat Enterprise Linux 6 (64-bit)"),
    (r"red\s*hat.*9",                     "Red Hat Enterprise Linux 9 (64-bit)"),
    (r"red\s*hat.*8",                     "Red Hat Enterprise Linux 8 (64-bit)"),
    (r"red\s*hat.*7",                     "Red Hat Enterprise Linux 7 (64-bit)"),
    (r"red\s*hat.*6",                     "Red Hat Enterprise Linux 6 (64-bit)"),
    (r"red\s*hat",                        "Red Hat Enterprise Linux 8 (64-bit)"),
    # ── SUSE / SLES ───────────────────────────────────────────────────────────
    (r"sles\s*15",                        "SUSE Linux Enterprise 15 (64-bit)"),
    (r"sles\s*12",                        "SUSE Linux Enterprise 12 (64-bit)"),
    (r"suse.*15",                         "SUSE Linux Enterprise 15 (64-bit)"),
    (r"suse.*12",                         "SUSE Linux Enterprise 12 (64-bit)"),
    (r"suse",                             "SUSE Linux Enterprise 15 (64-bit)"),
    # ── Ubuntu ────────────────────────────────────────────────────────────────
    (r"ubuntu\s*2[23]",                   "Ubuntu Linux (64-bit)"),
    (r"ubuntu\s*20",                      "Ubuntu Linux (64-bit)"),
    (r"ubuntu\s*18",                      "Ubuntu Linux (64-bit)"),
    (r"ubuntu",                           "Ubuntu Linux (64-bit)"),
    # ── Debian ────────────────────────────────────────────────────────────────
    (r"debian",                           "Debian GNU/Linux (64-bit)"),
    # ── CentOS ────────────────────────────────────────────────────────────────
    (r"centos\s*[89]",                    "CentOS Linux (64-bit)"),
    (r"centos\s*7",                       "CentOS 4/5/6/7 (64-bit)"),
    (r"centos",                           "CentOS Linux (64-bit)"),
    # ── Oracle Linux ──────────────────────────────────────────────────────────
    (r"oracle.*linux.*[89]",              "Oracle Linux 8 and later (64-bit)"),
    (r"oracle.*linux.*7",                 "Oracle Linux 7 (64-bit)"),
    (r"oracle.*linux",                    "Oracle Linux 8 and later (64-bit)"),
    # ── Rocky Linux ───────────────────────────────────────────────────────────
    (r"rocky.*linux.*9",                  "Rocky Linux (64-bit)"),
    (r"rocky.*linux.*8",                  "Rocky Linux (64-bit)"),
    (r"rocky.*linux",                     "Rocky Linux (64-bit)"),
    # ── AlmaLinux ─────────────────────────────────────────────────────────────
    (r"alma.*linux.*9",                   "AlmaLinux (64-bit)"),
    (r"alma.*linux",                      "AlmaLinux (64-bit)"),
    (r"almalinux",                        "AlmaLinux (64-bit)"),
    # ── Fedora CoreOS ─────────────────────────────────────────────────────────
    (r"fedora.*coreos",                   "Fedora CoreOS (64-bit)"),
    (r"coreos",                           "Fedora CoreOS (64-bit)"),
    # ── Windows Server ────────────────────────────────────────────────────────
    (r"windows.*server.*2022",            "Microsoft Windows Server 2022 (64-bit)"),
    (r"windows.*server.*2019",            "Microsoft Windows Server 2019 (64-bit)"),
    (r"windows.*server.*2016",            "Microsoft Windows Server 2016 (64-bit)"),
    (r"windows.*server.*2012.*r2",        "Microsoft Windows Server 2012 R2 (64-bit)"),
    (r"windows.*server.*2012",            "Microsoft Windows Server 2012 (64-bit)"),
    (r"windows.*server.*2008.*r2",        "Microsoft Windows Server 2008 R2 (64-bit)"),
    (r"windows.*server.*2008",            "Microsoft Windows Server 2008 (64-bit)"),
    (r"win.*2022",                        "Microsoft Windows Server 2022 (64-bit)"),
    (r"win.*2019",                        "Microsoft Windows Server 2019 (64-bit)"),
    (r"win.*2016",                        "Microsoft Windows Server 2016 (64-bit)"),
    (r"win.*2012\s*r2",                   "Microsoft Windows Server 2012 R2 (64-bit)"),
    (r"win.*2012",                        "Microsoft Windows Server 2012 (64-bit)"),
    (r"win.*2008\s*r2",                   "Microsoft Windows Server 2008 R2 (64-bit)"),
    (r"win.*2008",                        "Microsoft Windows Server 2008 (64-bit)"),
    # ── IBM i / OS/400 ────────────────────────────────────────────────────────
    (r"ibm\s*i\s*mol",                    "IBM i (OS/400)"),  # MOL variant — same normalization
    (r"ibm\s*i\b",                        "IBM i (OS/400)"),
    (r"i/os",                             "IBM i (OS/400)"),
    (r"os/400",                           "IBM i (OS/400)"),
    # ── AIX ───────────────────────────────────────────────────────────────────
    (r"aix\s*7",                          "IBM AIX 7.x"),
    (r"aix\s*6",                          "IBM AIX 6.x"),
    (r"aix",                              "IBM AIX 7.x"),
]

# Pre-compile the patterns once at import time
_OS_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(pattern, re.IGNORECASE), replacement)
    for pattern, replacement in _OS_NORMALIZATION
]


def _normalize_os_name(raw_os: str | None) -> tuple[str, bool]:
    """Return (normalized_os_name, was_changed).

    Matches the raw OS string against known patterns and returns the
    IBM-standard equivalent. Returns the input unchanged if no match.
    """
    if not raw_os:
        return raw_os or "", False
    for pattern, replacement in _OS_PATTERNS:
        if pattern.search(raw_os):
            if replacement.lower() != raw_os.lower():
                return replacement, True
            return replacement, False
    # Already has "(64-bit)" — likely already normalized
    if "(64-bit)" in raw_os:
        return raw_os, False
    return raw_os, False


# ---------------------------------------------------------------------------
# Sanity-check / post-processing
# ---------------------------------------------------------------------------

# 32 TB in MB — any disk or RAM value above this is clearly an LLM unit error
_MAX_DISK_MB = 32 * 1024 * 1024   # 32 TB
_MAX_RAM_MB  = 4 * 1024 * 1024    # 4 TB (generous upper bound for a single VM)
# Reasonable vCPU ceiling for a single VM
_MAX_CPUS    = 256

# IBM Cloud VPC boot volume constraints — applied at normalisation time so the
# clamping is recorded as an Assumption visible on the Review page and in the
# AI Assumptions Report.  The vpc_calculator_generator reads the already-clamped
# provisioned_mb and applies matching logic at export time (Sub-Task 1).
_IBM_VPC_BOOT_MIN_MB = 100 * 1024   # 100 GB minimum boot volume
_IBM_VPC_BOOT_MAX_MB = 250 * 1024   # 250 GB maximum boot volume


def _clamp_mb(value: object, label: str, assumptions_out: list[dict], max_mb: int) -> int:
    """Return a clamped MB integer and append an assumption if the value was adjusted."""
    try:
        v = int(value)
    except (TypeError, ValueError):
        return 0
    if v > max_mb:
        corrected = max_mb
        assumptions_out.append({
            "field_name": label,
            "assumed_value": str(corrected),
            "original_value": str(v),
            "reasoning": (
                f"LLM returned {v} MB which exceeds the sanity ceiling of {max_mb} MB "
                f"({max_mb // 1024} GB). Likely a unit-multiplication error (e.g. GB × 1024 × 10). "
                "Value capped at ceiling."
            ),
            "confidence": "medium",
        })
        logger.warning("Clamped %s from %d MB to %d MB (sanity ceiling)", label, v, corrected)
        return corrected
    return max(v, 0)


# Threshold below which a memory value is assumed to be in GB (not MB) and needs * 1024
# A real VM with < 512 MB RAM is essentially impossible in any modern workload.
_MIN_PLAUSIBLE_RAM_MB = 512


def _sanitize_numeric_fields(result: dict) -> dict:
    """Walk the normalised result and fix data quality issues from the LLM.

    Enforces:
    - Memory and disk values are in MB (auto-converts probable GB values)
    - template field is the string "FALSE" not a Python bool
    - vm_name does not contain the host suffix
    - nics / disks default to 1 when null
    - os_vmware_tools mirrors os_config (never a status string like 'toolsOk')
    - Numeric sanity caps

    Mutates result in-place and returns it.
    Appends corrective assumptions for every value changed.
    """
    new_assumptions: list[dict] = []

    # --- vinfo ---
    vinfo = result.get("vinfo") or {}
    if vinfo:
        # Fix 1: vm_name must not contain the host suffix the LLM sometimes copies
        raw_vm_name = str(vinfo.get("vm_name") or "unknown")
        if raw_vm_name.endswith("-host.customer.com"):
            fixed_name = raw_vm_name[: -len("-host.customer.com")]
            vinfo["vm_name"] = fixed_name
            new_assumptions.append({
                "field_name": "vinfo/vm_name",
                "assumed_value": fixed_name,
                "original_value": raw_vm_name,
                "reasoning": "LLM appended host suffix to vm_name; stripped to get server name.",
                "confidence": "medium",
            })

        # Fix 2: template must be the string "FALSE" not a Python/JSON bool
        if vinfo.get("template") is not True:   # True would mean it's a template — keep that
            vinfo["template"] = "FALSE"

        # Fix 3: memory — auto-detect if LLM returned GB instead of MB
        raw_mem = vinfo.get("memory_mb", 0)
        try:
            mem_val = int(float(raw_mem))
        except (TypeError, ValueError):
            mem_val = 0
        if 0 < mem_val < _MIN_PLAUSIBLE_RAM_MB:
            # Almost certainly in GB — convert
            corrected = mem_val * 1024
            new_assumptions.append({
                "field_name": "vinfo/memory_mb",
                "assumed_value": str(corrected),
                "original_value": str(mem_val),
                "reasoning": (
                    f"LLM returned memory_mb={mem_val} which is below the plausible minimum "
                    f"of {_MIN_PLAUSIBLE_RAM_MB} MB. Value treated as GB and converted to "
                    f"{corrected} MB."
                ),
                "confidence": "medium",
            })
            mem_val = corrected
        vinfo["memory_mb"] = _clamp_mb(mem_val, "vinfo/memory_mb", new_assumptions, _MAX_RAM_MB)

        # ── Disk unit detection ───────────────────────────────────────────────
        # Customer spreadsheets frequently label disk columns as "Disk (GB)" or
        # "Storage (GB)".  The LLM is instructed to multiply GB×1024 but often
        # passes the raw GB number directly as provisioned_mb.  We cross-check
        # the LLM's value against any raw GB column in the source data and
        # correct when the LLM value is implausibly small relative to the raw GB.
        #
        # Detection heuristic: if the raw_data dict contains a key whose name
        # contains "GB" (case-insensitive) and the value is a positive number,
        # and the LLM's provisioned_mb is less than (raw_gb × 512) — i.e., the
        # LLM appears to have treated GB as MB — we override with raw_gb × 1024.
        raw_data_ref = result.get("_raw_data") or {}
        _corrected_from_raw_gb = False
        for raw_key, raw_val in raw_data_ref.items():
            key_lower = str(raw_key).lower()
            if "gb" in key_lower and ("disk" in key_lower or "storage" in key_lower or "provisioned" in key_lower):
                try:
                    raw_gb_val = float(raw_val)
                except (TypeError, ValueError):
                    continue
                if raw_gb_val <= 0:
                    continue
                raw_as_mb = raw_gb_val * 1024
                llm_prov = float(vinfo.get("provisioned_mb") or 0)
                # If LLM value is < half of what raw_gb×1024 would be, the LLM
                # almost certainly passed the GB number straight through as MB.
                if llm_prov < raw_as_mb * 0.5:
                    corrected_mb = int(raw_as_mb)
                    logger.warning(
                        "Disk unit mismatch detected for '%s': LLM gave %s MB but raw "
                        "'%s'=%s GB → correcting to %d MB",
                        vinfo.get("vm_name"), llm_prov, raw_key, raw_gb_val, corrected_mb,
                    )
                    new_assumptions.append({
                        "field_name": "vinfo/provisioned_mb",
                        "assumed_value": str(corrected_mb),
                        "original_value": str(int(llm_prov)),
                        "reasoning": (
                            f"LLM returned provisioned_mb={int(llm_prov)} which appears to be "
                            f"the raw GB value ({raw_gb_val} GB) passed through without "
                            f"converting to MB. Corrected to {corrected_mb} MB "
                            f"({round(raw_gb_val, 1)} GB × 1024) using raw column '{raw_key}'."
                        ),
                        "confidence": "high",
                    })
                    vinfo["provisioned_mb"] = corrected_mb
                    _corrected_from_raw_gb = True
                    break  # first matching GB column wins

        # Capture original provisioned_mb (the true full disk size, pre-IBM-VPC-clamping)
        # and persist it as total_disk_mb so the vpc_calculator_generator can use the
        # full customer disk size to compute the Data Volume correctly even after the
        # boot disk is capped to 250 GB.
        original_prov = int(vinfo.get("provisioned_mb") or 0)

        vinfo["provisioned_mb"]  = _clamp_mb(vinfo.get("provisioned_mb", 0),  "vinfo/provisioned_mb",  new_assumptions, _MAX_DISK_MB)
        vinfo["in_use_mb"]       = _clamp_mb(vinfo.get("in_use_mb", 0),       "vinfo/in_use_mb",       new_assumptions, _MAX_DISK_MB)

        # Store the full customer disk size BEFORE IBM VPC boot clamping.
        # This value is used by vpc_calculator_generator to compute Data Volume size:
        #   data_gb = max(0, total_disk_gb - 250)
        vinfo["total_disk_mb"] = vinfo["provisioned_mb"]

        # IBM Cloud VPC boot volume constraints (applies to x86 VSIs only).
        # We clamp here at normalisation time so the adjustment is visible in the
        # Review page AssumptionsPanel and in the AI Assumptions Report.
        # The vpc_calculator_generator mirrors this logic at export time for the
        # Boot Volume Size (GB) and Data Volume Size (GB) columns.
        prov_mb = vinfo["provisioned_mb"]
        if prov_mb < _IBM_VPC_BOOT_MIN_MB:
            original_gb = round(prov_mb / 1024, 1)
            vinfo["provisioned_mb"] = _IBM_VPC_BOOT_MIN_MB
            new_assumptions.append({
                "field_name": "vinfo/provisioned_mb",
                "assumed_value": str(_IBM_VPC_BOOT_MIN_MB),
                "original_value": str(prov_mb),
                "reasoning": (
                    f"IBM Cloud VPC boot volume minimum is 100 GB. Customer-provided disk "
                    f"size of {original_gb} GB ({prov_mb} MB) is below this threshold and "
                    f"has been raised to 100 GB (102,400 MB). Please confirm the correct "
                    f"disk size with the customer."
                ),
                "confidence": "medium",
            })
            logger.info(
                "IBM VPC boot disk clamped UP: %d MB → %d MB (was below 100 GB minimum)",
                prov_mb, _IBM_VPC_BOOT_MIN_MB,
            )
        elif prov_mb > _IBM_VPC_BOOT_MAX_MB:
            original_gb = round(prov_mb / 1024, 1)
            overflow_mb = prov_mb - _IBM_VPC_BOOT_MAX_MB
            overflow_gb = round(overflow_mb / 1024, 1)
            vinfo["provisioned_mb"] = _IBM_VPC_BOOT_MAX_MB
            new_assumptions.append({
                "field_name": "vinfo/provisioned_mb",
                "assumed_value": str(_IBM_VPC_BOOT_MAX_MB),
                "original_value": str(prov_mb),
                "reasoning": (
                    f"IBM Cloud VPC boot volume maximum is 250 GB. Customer-provided disk "
                    f"size of {original_gb} GB ({prov_mb} MB) exceeds this limit. Boot "
                    f"disk has been set to 250 GB (256,000 MB). The excess {overflow_gb} GB "
                    f"({overflow_mb} MB) will be added as a separate Data Volume in the "
                    f"Cloud Solution Export. Confirm data volume requirements with customer."
                ),
                "confidence": "medium",
            })
            logger.info(
                "IBM VPC boot disk clamped DOWN: %d MB → %d MB (%.1f GB overflow → Data Volume)",
                prov_mb, _IBM_VPC_BOOT_MAX_MB, overflow_gb,
            )

        # Recalculate in_use_mb if it was AI-estimated at 60% of the original provisioned_mb.
        # If the customer provided a real in_use_mb it won't match exactly 60% so we leave it.
        if original_prov > 0 and vinfo["in_use_mb"] == round(original_prov * 0.6):
            vinfo["in_use_mb"] = round(vinfo["provisioned_mb"] * 0.6)

        # Fix 4: nics and disks must be non-null integers >= 1
        try:
            nics = int(vinfo.get("nics") or 1)
            vinfo["nics"] = max(nics, 1)
        except (TypeError, ValueError):
            vinfo["nics"] = 1
        try:
            disks_val = vinfo.get("disks")
            disks = int(float(disks_val)) if disks_val is not None else 1
            vinfo["disks"] = max(disks, 1)
        except (TypeError, ValueError):
            vinfo["disks"] = 1

        try:
            cpus = int(vinfo.get("cpus", 1))
            if cpus > _MAX_CPUS:
                new_assumptions.append({
                    "field_name": "vinfo/cpus",
                    "assumed_value": str(_MAX_CPUS),
                    "original_value": str(cpus),
                    "reasoning": f"CPU count {cpus} exceeds sanity ceiling {_MAX_CPUS}. Capped.",
                    "confidence": "medium",
                })
                cpus = _MAX_CPUS
            vinfo["cpus"] = max(cpus, 1)
        except (TypeError, ValueError):
            vinfo["cpus"] = 1

        # in_use_mb must be <= provisioned_mb
        if vinfo["in_use_mb"] > vinfo["provisioned_mb"] and vinfo["provisioned_mb"] > 0:
            vinfo["in_use_mb"] = vinfo["provisioned_mb"]

        # Fix 5: Normalize OS names to IBM-standard strings
        raw_os = vinfo.get("os_config") or ""
        normalized_os, os_changed = _normalize_os_name(raw_os)
        if os_changed:
            vinfo["os_config"] = normalized_os
            new_assumptions.append({
                "field_name": "vinfo/os_config",
                "assumed_value": normalized_os,
                "original_value": raw_os,
                "reasoning": (
                    f"OS name '{raw_os}' normalized to IBM/VMware-standard string "
                    f"'{normalized_os}' for RVTools compatibility."
                ),
                "confidence": "high",
            })

        # Fix 6: os_vmware_tools must mirror os_config — NEVER be a status string
        _TOOLS_STATUS_STRINGS = {
            "toolsok", "toolsnotinstalled", "toolsold", "toolsnotrunning",
            "guesttoolsnotinstalled", "guesttoolsnotrunning",
        }
        raw_tools_os = str(vinfo.get("os_vmware_tools") or "")
        if raw_tools_os.lower().strip() in _TOOLS_STATUS_STRINGS or not raw_tools_os.strip():
            # Use the already-normalized os_config value
            vinfo["os_vmware_tools"] = vinfo.get("os_config") or normalized_os
        else:
            norm_tools_os, tools_changed = _normalize_os_name(raw_tools_os)
            if tools_changed:
                vinfo["os_vmware_tools"] = norm_tools_os

    # --- vpartition ---
    _MIN_DISK_MB = 10   # anything below 10 MB is almost certainly in GB
    for part in result.get("vpartition") or []:
        if not isinstance(part, dict):   # guard: LLM sometimes returns list of strings
            continue
        # Auto-convert disk values that look like GB
        raw_cap = part.get("capacity_mb", 0)
        try:
            cap_val = int(float(raw_cap))
        except (TypeError, ValueError):
            cap_val = 0
        if 0 < cap_val < _MIN_DISK_MB:
            cap_val = cap_val * 1024
        cap  = _clamp_mb(cap_val,                      "vpartition/capacity_mb",  new_assumptions, _MAX_DISK_MB)
        cons = _clamp_mb(part.get("consumed_mb", 0),   "vpartition/consumed_mb",  new_assumptions, _MAX_DISK_MB)
        part["capacity_mb"] = cap
        part["consumed_mb"] = min(cons, cap) if cap > 0 else cons
        part["free_mb"]     = max(cap - part["consumed_mb"], 0)
        part["free_pct"]    = round(part["free_mb"] / cap * 100, 1) if cap > 0 else 0.0
        # Fix template field in vpartition too
        part["template"] = "FALSE"

    # --- vnetwork — inject gateway/DNS/security-group assumptions for placeholder IPs ---
    vm_name = (result.get("vinfo") or {}).get("vm_name", "unknown")
    for idx, nic in enumerate(result.get("vnetwork") or []):
        if not isinstance(nic, dict):   # guard: LLM sometimes returns list of strings
            continue
        ipv4 = nic.get("ipv4_address") or ""
        is_placeholder = (
            not ipv4
            or ipv4.startswith("10.0.0.x")
            or ipv4.endswith(".x")
            or ipv4 in ("", "0.0.0.0", "N/A", "n/a")
        )
        if is_placeholder:
            net_assumptions = get_network_assumptions(vm_name, idx, provided_ip=None if is_placeholder else ipv4)
            new_assumptions.extend(net_assumptions)

    # Guard: ensure every element in the merged assumptions list is a dict
    # so downstream code can safely call .get() on each item.
    raw_assumptions = list(result.get("assumptions") or [])
    safe_assumptions = [a for a in raw_assumptions if isinstance(a, dict)]
    result["assumptions"] = safe_assumptions + new_assumptions
    return result


# ---------------------------------------------------------------------------
# Python fallback synthesizer — used when Ollama returns unparseable output
# ---------------------------------------------------------------------------

def _synthesize_from_raw(raw_data: dict) -> dict:
    """Build a minimal but valid normalized record purely from raw_data.

    Called when every Ollama attempt fails. Values are best-effort from the
    raw data; everything inferred is marked as a low-confidence assumption.
    """
    from services.network_inference import infer_server_type

    renamed = _rename_unnamed_columns(raw_data)

    def _pick(*keys):
        for k in keys:
            v = renamed.get(k)
            if v is not None and str(v).strip() not in ("", "nan", "NaN", "None"):
                return v
        return None

    vm_name    = str(_pick("server_name", "name", "vm_name", "hostname") or "unknown")

    # Guard: if vm_name looks like a header row, mark it clearly and use safe defaults
    _HEADER_SENTINELS = {"devicename", "device name", "server name", "vm name", "hostname", "name"}
    if vm_name.lower().strip() in _HEADER_SENTINELS:
        vm_name = f"HEADER_ROW_{vm_name}"

    os_raw     = str(_pick("os", "operating_system", "os_type") or "Unknown OS")

    def _safe_int(val, default):
        """Convert val to int, returning default if it's not numeric."""
        try:
            return int(float(val))
        except (TypeError, ValueError):
            return default

    vcpus      = _safe_int(_pick("vcpus", "cpu_count", "cpus"), 2)
    # ram_mb_or_disk_mb col 8 is RAM in MB for most rows in this dataset
    ram_raw    = _pick("ram_mb_or_disk_mb", "memory_mb", "ram_mb", "ram_gb")
    mem_mb     = _safe_int(ram_raw, 4096)
    disk_raw   = _pick("disk_gb", "disk_mb", "storage_gb")
    disk_mb    = _safe_int(float(disk_raw) * 1024 if disk_raw else None, 51200)
    # PowerVS detection takes priority over generic server_type inference
    if _is_powervs_os(os_raw):
        server_type = "powervs"
    else:
        server_type = infer_server_type(raw_data)

    os_config, _ = _normalize_os_name(os_raw)
    os_tools  = os_config   # mirror os_config — never use status strings here
    host      = f"{vm_name}-host.customer.com"
    dc        = str(_pick("datacenter", "cluster_type") or "Datacenter1")
    cluster   = str(_pick("pool_or_cluster_name", "cluster") or "Cluster1")

    vinfo = {
        "vm_name": vm_name, "powerstate": "poweredOn", "template": "False",
        "cpus": vcpus, "memory_mb": mem_mb, "nics": 1, "disks": 1,
        "provisioned_mb": disk_mb, "in_use_mb": int(disk_mb * 0.6),
        "datacenter": dc, "cluster": cluster, "host": host,
        "os_config": os_config, "os_vmware_tools": os_tools,
    }
    vnetwork = [{
        "vm_name": vm_name, "powerstate": "poweredOn", "template": "False",
        "srm_placeholder": "False", "nic_label": "Network adapter 1",
        "adapter": "Vmxnet3" if server_type == "vm" else "E1000e",
        "network": "VM Network", "switch": "vSwitch0",
        "connected": "True", "starts_connected": "True",
        "mac_address": "00:50:56:00:00:01",
        "type": "VirtualVmxnet3" if server_type == "vm" else "VirtualE1000e",
        "ipv4_address": "10.0.1.2", "ipv6_address": "",
        "direct_path_io": "False", "internal_sort_column": 0, "annotation": "",
    }]
    vpartition = [{
        "vm_name": vm_name, "powerstate": "poweredOn", "template": "False",
        "disk_label": "C:\\" if "windows" in os_raw.lower() else "/",
        "capacity_mb": disk_mb, "consumed_mb": int(disk_mb * 0.6),
        "free_mb": int(disk_mb * 0.4), "free_pct": 40.0,
        "datacenter": dc, "cluster": cluster, "host": host,
        "os_config": os_config, "os_vmware_tools": os_tools,
    }]
    assumptions = [
        {
            "field_name": "all_fields",
            "assumed_value": "synthesized from raw data",
            "original_value": None,
            "reasoning": "LLM normalization failed for this record — all values synthesized directly from raw spreadsheet data using Python defaults.",
            "confidence": "low",
        }
    ]
    if server_type == "powervs":
        assumptions.append(dict(_POWERVS_ASSUMPTION))
    return {
        "server_type": server_type,
        "vinfo": vinfo,
        "vnetwork": vnetwork,
        "vpartition": vpartition,
        "assumptions": assumptions,
    }


# ---------------------------------------------------------------------------
# JSON repair
# ---------------------------------------------------------------------------

def _repair_truncated_json(text: str) -> str:
    """Attempt to close a truncated JSON object by balancing brackets.

    When the LLM hits the token limit mid-object, the JSON ends abruptly.
    Strategy:
      1. Strip any trailing incomplete key-value (dangling key with no value)
      2. Close any open arrays with []
      3. Close any open objects with {}
      4. Ensure required top-level keys exist with empty defaults
    """
    import re as _re

    # Remove trailing garbage: dangling open string, incomplete key, or bare comma
    # e.g. ends with:  "  |  "key":  |  "key": val,  |  ,
    text = text.rstrip()
    # Strip dangling unclosed string at the very end (e.g. the text ends with just  "  )
    text = _re.sub(r',?\s*"[^"]*$', '', text)
    # Strip incomplete key-value  "key":  (key present but no value)
    text = _re.sub(r',?\s*"[^"]+"\s*:\s*$', '', text.rstrip())
    # Strip trailing comma
    text = text.rstrip().rstrip(',')

    # Count unmatched open braces/brackets
    depth_brace  = text.count('{') - text.count('}')
    depth_bracket = text.count('[') - text.count(']')

    # Close open arrays first, then objects
    text = text.rstrip().rstrip(',')
    text += ']' * max(0, depth_bracket)
    text += '}' * max(0, depth_brace)

    # Ensure top-level required keys exist
    try:
        partial = json.loads(text)
    except json.JSONDecodeError:
        return text

    for key, default in [("server_type", "vm"), ("vinfo", {}), ("vnetwork", []), ("vpartition", []), ("assumptions", [])]:
        if key not in partial:
            partial[key] = default
    # Ensure vinfo has vm_name
    if isinstance(partial.get("vinfo"), dict) and not partial["vinfo"].get("vm_name"):
        partial["vinfo"]["vm_name"] = "unknown"

    return json.dumps(partial)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Ollama call — with timeout and retry
# ---------------------------------------------------------------------------

# Per-record timeout: 120 s is ~10× the average phi4-mini response time.
# If Ollama hangs longer than this the record falls back to the Python synthesizer
# instead of blocking the entire queue for 5 minutes.
_OLLAMA_TIMEOUT_SECONDS = 120.0
_MAX_RETRIES = 1   # retry once on timeout/connect error before falling back

# IAM token cache: { api_key_hash -> (token, expiry_epoch) }
# Tokens expire at 60 min; we refresh at 50 min to be safe.
_IAM_TOKEN_CACHE: dict[str, tuple[str, float]] = {}
_IAM_TOKEN_TTL = 50 * 60  # 50 minutes in seconds


def _call_ollama(payload: dict) -> str:
    """POST to Ollama /api/generate with timeout and retry.

    Returns the raw response text string.
    Raises ValueError on all unrecoverable errors.
    """
    url = f"{settings.ollama_base_url}/api/generate"
    last_exc: Exception | None = None

    for attempt in range(1, _MAX_RETRIES + 2):   # attempts = retries + 1 original
        try:
            with httpx.Client(timeout=_OLLAMA_TIMEOUT_SECONDS) as client:
                response = client.post(url, json=payload)
                response.raise_for_status()
            raw_text: str = response.json().get("response", "")
            if not raw_text:
                raise ValueError(
                    "Ollama returned an empty response. "
                    "The model may still be loading — wait a moment and retry."
                )
            return raw_text
        except httpx.ConnectError as exc:
            raise ValueError(
                f"Cannot reach Ollama at {settings.ollama_base_url}. "
                "Make sure the Ollama app is running on your Mac (look for the llama "
                "icon in the menu bar), then try again."
            ) from exc
        except httpx.TimeoutException as exc:
            last_exc = exc
            logger.warning(
                "Ollama request timed out after %.0fs (attempt %d/%d)",
                _OLLAMA_TIMEOUT_SECONDS, attempt, _MAX_RETRIES + 1,
            )
            # Brief pause before retry so Ollama can clear its queue
            import time; time.sleep(2)
            continue
        except httpx.HTTPStatusError as exc:
            raise ValueError(
                f"Ollama returned HTTP {exc.response.status_code}: {exc.response.text[:300]}"
            ) from exc

    raise ValueError(
        f"Ollama timed out after {_MAX_RETRIES + 1} attempt(s) "
        f"({_OLLAMA_TIMEOUT_SECONDS:.0f}s each). "
        "Record will be synthesized from raw data."
    ) from last_exc


# ---------------------------------------------------------------------------
# Cloud LLM adapters
# ---------------------------------------------------------------------------

def _call_watsonx(prompt_text: str, settings_row: "LLMSettings") -> str:  # type: ignore[name-defined]
    """Call IBM watsonx.ai with IAM token (cached for 50 min)."""
    import hashlib
    import time as _time

    api_key = _decrypt_safe(settings_row.watsonx_api_key_enc)
    if not api_key:
        raise ValueError("watsonx API key not configured — set it in Settings.")
    project_id = settings_row.watsonx_project_id
    if not project_id:
        raise ValueError("watsonx Project ID not configured — set it in Settings.")
    watsonx_url = settings_row.watsonx_url or "https://us-south.ml.cloud.ibm.com"
    model = settings_row.watsonx_model or "ibm/granite-3-8b-instruct"

    # IAM token — use cache to avoid hitting IAM on every record
    cache_key = hashlib.sha256(api_key.encode()).hexdigest()[:16]
    now = _time.time()
    if cache_key in _IAM_TOKEN_CACHE:
        token, expiry = _IAM_TOKEN_CACHE[cache_key]
        if now < expiry:
            pass  # cache hit
        else:
            del _IAM_TOKEN_CACHE[cache_key]
            token = None
    else:
        token = None

    if token is None:
        iam_resp = httpx.post(
            "https://iam.cloud.ibm.com/identity/token",
            data={"grant_type": "urn:ibm:params:oauth:grant-type:apikey", "apikey": api_key},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=20.0,
        )
        iam_resp.raise_for_status()
        token = iam_resp.json()["access_token"]
        _IAM_TOKEN_CACHE[cache_key] = (token, now + _IAM_TOKEN_TTL)

    resp = httpx.post(
        f"{watsonx_url}/ml/v1/text/generation?version=2024-01-01",
        json={
            "model_id": model,
            "input": f"{_SYSTEM_PROMPT}\n\nServer data:\n{prompt_text}",
            "project_id": project_id,
            "parameters": {"max_new_tokens": 3000, "temperature": 0},
        },
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=_OLLAMA_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    return resp.json()["results"][0]["generated_text"]


def _call_openai(prompt_text: str, settings_row: "LLMSettings") -> str:  # type: ignore[name-defined]
    """Call an OpenAI-compatible /v1/chat/completions endpoint."""
    api_key = _decrypt_safe(settings_row.openai_api_key_enc)
    if not api_key:
        raise ValueError("OpenAI API key not configured — set it in Settings.")
    base_url = settings_row.openai_base_url or "https://api.openai.com"
    model = settings_row.openai_model or "gpt-4o-mini"

    resp = httpx.post(
        f"{base_url}/v1/chat/completions",
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": f"Server data:\n{prompt_text}"},
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": 3000,
            "temperature": 0,
        },
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        timeout=_OLLAMA_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def _call_anthropic(prompt_text: str, settings_row: "LLMSettings") -> str:  # type: ignore[name-defined]
    """Call Anthropic Claude via /v1/messages."""
    api_key = _decrypt_safe(settings_row.anthropic_api_key_enc)
    if not api_key:
        raise ValueError("Anthropic API key not configured — set it in Settings.")
    model = settings_row.anthropic_model or "claude-3-haiku-20240307"

    resp = httpx.post(
        "https://api.anthropic.com/v1/messages",
        json={
            "model": model,
            "max_tokens": 3000,
            "system": _SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": f"Server data:\n{prompt_text}"}],
        },
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
        timeout=_OLLAMA_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    return resp.json()["content"][0]["text"]


def _decrypt_safe(enc_value: str | None) -> str:
    """Decrypt an encrypted field; return empty string on any failure."""
    if not enc_value:
        return ""
    try:
        from services.crypto import decrypt
        return decrypt(enc_value)
    except Exception:  # noqa: BLE001
        return ""


def _get_active_settings():
    """Read the active LLMSettings row from the DB synchronously.

    `normalize_record` runs in a background thread (not an async context),
    so we use a regular synchronous SQLAlchemy engine.
    Returns None if the table is unavailable (e.g. during initial migration).
    """
    try:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session
        from db.models import LLMSettings
        from core.config import settings as cfg

        sync_url = cfg.database_url.replace("+asyncpg", "")
        engine = create_engine(sync_url, pool_size=1, max_overflow=0)
        with Session(engine) as session:
            row = session.get(LLMSettings, 1)
        engine.dispose()
        return row
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not read LLM settings from DB (%s) — defaulting to Ollama", exc)
        return None


def _call_llm(raw_data: dict) -> tuple[str, dict]:
    """Dispatch to the active LLM provider and return (raw_text, ollama_payload).

    Returns (raw_text, {}) for cloud providers (raw_text is the JSON string).
    Returns ("", payload) for Ollama (caller uses _call_ollama(payload)).

    Raises ValueError on failure — caller falls back to Python synthesizer.
    """
    prompt_text = _build_prompt(raw_data)
    row = _get_active_settings()
    provider = (row.provider if row else "ollama")

    if provider == "watsonx" and row:
        logger.info("LLM dispatch → watsonx (%s)", row.watsonx_model or "granite-3-8b")
        return _call_watsonx(prompt_text, row), {}

    if provider == "openai" and row:
        logger.info("LLM dispatch → openai (%s)", row.openai_model or "gpt-4o-mini")
        return _call_openai(prompt_text, row), {}

    if provider == "anthropic" and row:
        logger.info("LLM dispatch → anthropic (%s)", row.anthropic_model or "claude-3-haiku")
        return _call_anthropic(prompt_text, row), {}

    # Default: Ollama
    logger.info("LLM dispatch → ollama (%s)", settings.ollama_model)
    ollama_payload = {
        "model": settings.ollama_model,
        "prompt": prompt_text,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0, "num_predict": 3000},
    }
    return "", ollama_payload


def normalize_record(raw_data: dict) -> dict:
    """Normalize a single raw server record using the active LLM provider.

    Dispatches to watsonx.ai, OpenAI, Anthropic, or Ollama depending on the
    active provider configured in Settings.  Falls back to the Python
    synthesizer if the LLM call fails for any reason.

    vHost is always synthesized in Python (not by the LLM) to stay
    within context limits.

    Returns a dict with keys:
        server_type, vinfo, vnetwork, vpartition, vhost, assumptions
    """
    try:
        raw_text, ollama_payload = _call_llm(raw_data)
        if ollama_payload:
            # Ollama path: use the dedicated caller with timeout/retry logic
            raw_text = _call_ollama(ollama_payload)
    except ValueError as exc:
        logger.warning("LLM failed (%s) — using Python synthesizer for this record", exc)
        return _synthesize_from_raw(raw_data)

    cleaned = _extract_json(raw_text)

    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError:
        repaired = _repair_truncated_json(cleaned)
        try:
            result = json.loads(repaired)
            logger.warning("Repaired truncated JSON (was %d chars)", len(cleaned))
        except json.JSONDecodeError:
            logger.warning(
                "Ollama JSON unrecoverable — Python synthesizer. Preview: %s",
                raw_text[:200],
            )
            return _synthesize_from_raw(raw_data)

    # Fill missing top-level keys with safe defaults
    for key, default in [("server_type", "vm"), ("vnetwork", []), ("vpartition", []), ("assumptions", [])]:
        if key not in result:
            result[key] = default
    if "vinfo" not in result:
        logger.warning("LLM response missing vinfo — using Python synthesizer")
        return _synthesize_from_raw(raw_data)

    # Stash the original raw_data on the result so _sanitize_numeric_fields can
    # cross-check disk/memory units against the raw column names/values.
    # Removed immediately after sanitization so it never reaches the DB.
    result["_raw_data"] = raw_data
    result = _sanitize_numeric_fields(result)
    result.pop("_raw_data", None)

    # ── PowerVS post-processor: override server_type and map IBM Cool OS family ──
    # The LLM should already return "powervs" per the prompt, but we enforce it
    # in Python as a guaranteed post-processing step regardless of LLM compliance.
    # Also handles Linux-on-Power variants (SAP Red Hat, SAP SUSE, Red Hat GP,
    # SUSE GP, Linux BYOL) which older prompts would have classified as x86.
    vinfo = result.get("vinfo", {})
    os_cfg_str = str(vinfo.get("os_config") or "")
    if _is_powervs_os(os_cfg_str) and result.get("server_type") != "powervs":
        result["server_type"] = "powervs"
        logger.info("PowerVS override applied for OS: %s", os_cfg_str)

    if result.get("server_type") == "powervs":
        # Ensure the server_type assumption is present (idempotent — only add once)
        existing_fields = {a.get("field_name") for a in result.get("assumptions", [])}
        if "server_type" not in existing_fields:
            result["assumptions"] = result.get("assumptions", []) + [dict(_POWERVS_ASSUMPTION)]

        # Map the OS string to one of the 8 IBM Cool PowerVS OS family strings
        # and store it in vinfo["powervs_os_family"].  The rvtools_generator writes
        # this value to the "OS according to the configuration file" column so
        # IBM Cool receives the correct pricing family.
        pvs_family = _map_powervs_os_family(os_cfg_str)
        if vinfo.get("powervs_os_family") != pvs_family:
            result["vinfo"]["powervs_os_family"] = pvs_family
            # Only record the assumption if the family differs from the raw OS string
            if pvs_family.lower() not in os_cfg_str.lower():
                result["assumptions"] = result.get("assumptions", []) + [{
                    "field_name": "vinfo/powervs_os_family",
                    "assumed_value": pvs_family,
                    "original_value": os_cfg_str or None,
                    "reasoning": (
                        f"OS string '{os_cfg_str}' mapped to IBM Cool PowerVS OS family "
                        f"'{pvs_family}'. This value is written to the 'OS according to the "
                        f"configuration file' column in the PowerVS RVTools export so IBM Cool "
                        f"applies the correct PowerVS pricing tier."
                    ),
                    "confidence": "high",
                }]
        logger.info("PowerVS OS family for '%s': %s", os_cfg_str, pvs_family)

    vhost, vhost_assumptions = _synthesize_vhost(
        vm_name=vinfo.get("vm_name", "unknown"),
        datacenter=vinfo.get("datacenter", "Datacenter1"),
        cluster=vinfo.get("cluster", "Cluster1"),
        memory_mb=int(vinfo.get("memory_mb", 4096)),
        cpus=int(vinfo.get("cpus", 2)),
    )
    result["vhost"] = vhost
    result["assumptions"] = result.get("assumptions", []) + vhost_assumptions

    return result
