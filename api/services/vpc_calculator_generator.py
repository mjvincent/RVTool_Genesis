"""IBM Cloud VPC Calculator workbook generator.

Produces the 3-sheet workbook consumed by the IBM Cloud Cost Estimator
(rvtools2vpc.vmware-solutions.cloud.ibm.com / IBM VPC Calculator):
  - Project Settings  — Zone, Subnet, and per-VM Compute + Data Volume rows
  - Exceptions        — VMs with no matching IBM VPC profile (flagged no_matching_profile)
  - Data Domains      — Static reference/lookup data (174 rows, never changes per-project)

Translation logic reverse-engineered from the sample file produced by the rvtools2vpc tool
using the Windows Servers 20216 Subset dataset.
"""
from __future__ import annotations

import io
import math
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

# ---------------------------------------------------------------------------
# IBM VPC Flex profile selection table
# Format: (min_cpus, max_cpus, min_ram_gb_per_cpu, max_ram_gb_per_cpu) -> (category, prefix)
#
# Rules derived from the IBM Cloud VPC instance profile families:
#   Flex-Compute  (cxf): ratio ≤ 2  GB/vCPU
#   Flex-Balanced (bxf): ratio  3–5 GB/vCPU
#   Flex-Memory   (mxf): ratio ≥ 6  GB/vCPU
#
# Profile name pattern: {prefix}-{cpu}x{ram}
# IBM Flex profiles allow any CPU count and any RAM as long as RAM is a multiple of
# the minimum ratio.  The nearest standard size that *covers* the requested spec is chosen.
# ---------------------------------------------------------------------------

_FLEX_PROFILE_RULES = [
    # (ratio_min, ratio_max_inclusive, category, prefix)
    (0.0,  2.5,  "Flex-Compute",  "cxf"),
    (2.5,  5.5,  "Flex-Balanced", "bxf"),
    (5.5,  99.0, "Flex-Memory",   "mxf"),
]

# IBM Flex profiles snap CPU counts to standard values:
_FLEX_CPU_SIZES = [1, 2, 4, 8, 12, 16, 20, 24, 32, 48, 64, 96, 128]

# IBM VPC standard RAM multiples per category (GB per vCPU baseline):
_FLEX_RAM_RATIO = {
    "cxf": 2,   # Flex-Compute  → 2 GB/vCPU baseline
    "bxf": 4,   # Flex-Balanced → 4 GB/vCPU baseline
    "mxf": 8,   # Flex-Memory   → 8 GB/vCPU baseline
}


def _select_vpc_profile(cpus: int, ram_gb: int) -> tuple[str, str, str]:
    """Return (category, family_str, issues_flag) for an IBM VPC flex profile.

    family_str is the full profile name e.g. 'cxf-8x16'.
    issues_flag is '' for a clean match or 'no_matching_profile' when the
    requested spec exceeds all standard profile sizes.
    """
    if cpus <= 0:
        cpus = 1
    if ram_gb <= 0:
        ram_gb = 1

    ratio = ram_gb / cpus

    # Pick category
    category, prefix = "Flex-Compute", "cxf"
    for r_min, r_max, cat, pfx in _FLEX_PROFILE_RULES:
        if r_min <= ratio <= r_max:
            category, prefix = cat, pfx
            break

    # Snap CPU to the next standard size >= requested
    snap_cpu = next((c for c in _FLEX_CPU_SIZES if c >= cpus), None)
    if snap_cpu is None:
        # Exceeds largest standard size
        return category, f"{prefix}-{cpus}x{ram_gb}", "no_matching_profile"

    # RAM = snap_cpu × baseline_ratio, rounded up to nearest multiple
    base_ratio = _FLEX_RAM_RATIO[prefix]
    snap_ram = snap_cpu * base_ratio
    # If the requested RAM is larger, round up to the next multiple
    if ram_gb > snap_ram:
        snap_ram = math.ceil(ram_gb / base_ratio) * base_ratio
        # Recalculate if this pushes us into another category
        new_ratio = snap_ram / snap_cpu
        for r_min, r_max, cat, pfx in _FLEX_PROFILE_RULES:
            if r_min <= new_ratio <= r_max:
                category, prefix = cat, pfx
                break
        snap_ram = snap_cpu * _FLEX_RAM_RATIO[prefix]
        if snap_ram < ram_gb:
            snap_ram = math.ceil(ram_gb / _FLEX_RAM_RATIO[prefix]) * _FLEX_RAM_RATIO[prefix]

    return category, f"{prefix}-{snap_cpu}x{snap_ram}", ""


# ---------------------------------------------------------------------------
# OS string → IBM VPC image name mapping
# ---------------------------------------------------------------------------

_OS_IMAGE_MAP: list[tuple[str, str, str]] = [
    # (substring_match_lower, os_family_name, ibm_image_id)
    # Windows
    ("windows server 2022",  "Windows Server", "ibm-windows-server-2022-amd64-9"),
    ("windows server 2019",  "Windows Server", "ibm-windows-server-2019-amd64-11"),
    ("windows server 2016",  "Windows Server", "ibm-windows-server-2016-amd64-12"),
    ("windows server 2012",  "Windows Server", "ibm-windows-server-2012-r2-amd64-12"),
    ("windows server 2008",  "Windows Server", "ibm-windows-server-2008-r2-amd64-12"),
    ("windows",              "Windows Server", "ibm-windows-server-2022-amd64-9"),
    # Red Hat Enterprise Linux
    ("red hat enterprise linux 9",  "Red Hat Enterprise Linux", "ibm-redhat-9-2-minimal-amd64-2"),
    ("red hat enterprise linux 8",  "Red Hat Enterprise Linux", "ibm-redhat-8-8-minimal-amd64-2"),
    ("red hat enterprise linux 7",  "Red Hat Enterprise Linux", "ibm-redhat-7-9-minimal-amd64-11"),
    ("red hat enterprise linux",    "Red Hat Enterprise Linux", "ibm-redhat-9-2-minimal-amd64-2"),
    ("rhel 9",   "Red Hat Enterprise Linux", "ibm-redhat-9-2-minimal-amd64-2"),
    ("rhel 8",   "Red Hat Enterprise Linux", "ibm-redhat-8-8-minimal-amd64-2"),
    ("rhel 7",   "Red Hat Enterprise Linux", "ibm-redhat-7-9-minimal-amd64-11"),
    ("rhel",     "Red Hat Enterprise Linux", "ibm-redhat-9-2-minimal-amd64-2"),
    # SUSE
    ("suse linux enterprise server 15", "SUSE Linux Enterprise Server", "ibm-sles-15-5-amd64-1"),
    ("suse linux enterprise server 12", "SUSE Linux Enterprise Server", "ibm-sles-12-5-amd64-6"),
    ("suse", "SUSE Linux Enterprise Server", "ibm-sles-15-5-amd64-1"),
    ("sles", "SUSE Linux Enterprise Server", "ibm-sles-15-5-amd64-1"),
    # Ubuntu
    ("ubuntu 22", "Ubuntu Linux", "ibm-ubuntu-22-04-6-minimal-amd64-2"),
    ("ubuntu 20", "Ubuntu Linux", "ibm-ubuntu-20-04-6-minimal-amd64-4"),
    ("ubuntu 18", "Ubuntu Linux", "ibm-ubuntu-18-04-6-minimal-amd64-4"),
    ("ubuntu",    "Ubuntu Linux", "ibm-ubuntu-22-04-6-minimal-amd64-2"),
    # Debian
    ("debian 12", "Debian GNU/Linux", "ibm-debian-12-0-minimal-amd64-1"),
    ("debian 11", "Debian GNU/Linux", "ibm-debian-11-7-minimal-amd64-2"),
    ("debian",    "Debian GNU/Linux", "ibm-debian-12-0-minimal-amd64-1"),
    # CentOS / CentOS Stream
    ("centos stream 9", "CentOS Stream", "ibm-centos-stream-9-amd64-4"),
    ("centos stream 8", "CentOS Stream", "ibm-centos-stream-8-amd64-4"),
    ("centos stream",   "CentOS Stream", "ibm-centos-stream-9-amd64-4"),
    ("centos 8",  "CentOS", "ibm-centos-7-9-minimal-amd64-12"),
    ("centos 7",  "CentOS", "ibm-centos-7-9-minimal-amd64-12"),
    ("centos",    "CentOS", "ibm-centos-7-9-minimal-amd64-12"),
    # Rocky Linux
    ("rocky linux 9", "Rocky Linux", "ibm-rocky-linux-9-2-minimal-amd64-1"),
    ("rocky linux 8", "Rocky Linux", "ibm-rocky-linux-8-8-minimal-amd64-2"),
    ("rocky linux",   "Rocky Linux", "ibm-rocky-linux-9-2-minimal-amd64-1"),
    # Fedora CoreOS
    ("fedora coreos",  "Fedora CoreOS", "ibm-fedora-coreos-38-stable-2"),
    ("fedora",         "Fedora CoreOS", "ibm-fedora-coreos-38-stable-2"),
    # Oracle Linux
    ("oracle linux 9", "Red Hat Enterprise Linux", "ibm-redhat-9-2-minimal-amd64-2"),
    ("oracle linux 8", "Red Hat Enterprise Linux", "ibm-redhat-8-8-minimal-amd64-2"),
    ("oracle linux",   "Red Hat Enterprise Linux", "ibm-redhat-9-2-minimal-amd64-2"),
    # Generic Linux fallback
    ("linux",  "CentOS", "ibm-centos-7-9-minimal-amd64-12"),
]


def _map_os_to_image(os_string: str | None) -> tuple[str, str]:
    """Return (os_family_name, ibm_image_id) for a given OS string.

    Falls back to CentOS 7 (the rvtools2vpc tool default) when no match.
    """
    if not os_string:
        return "CentOS", "ibm-centos-7-9-minimal-amd64-12"
    os_lower = os_string.lower()
    for substr, family, image in _OS_IMAGE_MAP:
        if substr in os_lower:
            return family, image
    # Unrecognised — use CentOS fallback
    return "CentOS", "ibm-centos-7-9-minimal-amd64-12"


# ---------------------------------------------------------------------------
# IBM Cloud geography / region / datacenter lookup
# ---------------------------------------------------------------------------

# Maps region → geography label (used in Zone/Subnet/DataVolume rows)
IBM_VPC_REGIONS: dict[str, str] = {
    "us-south":  "North America",
    "us-east":   "North America",
    "ca-tor":    "North America",
    "ca-mon":    "North America",
    "br-sao":    "South America",
    "eu-gb":     "Europe",
    "eu-de":     "Europe",
    "eu-es":     "Europe",
    "eu-fr2":    "Europe",
    "jp-tok":    "Asia Pacific",
    "jp-osa":    "Asia Pacific",
    "au-syd":    "Asia Pacific",
    "in-che":    "Asia Pacific",
    "kr-seo":    "Asia Pacific",
    "mx-qro":    "North America",
}

# Maps region → list of availability zones (datacenters)
IBM_VPC_DATACENTERS: dict[str, list[str]] = {
    "us-south":  ["us-south-1", "us-south-2", "us-south-3"],
    "us-east":   ["us-east-1",  "us-east-2",  "us-east-3"],
    "ca-tor":    ["ca-tor-1",   "ca-tor-2",   "ca-tor-3"],
    "ca-mon":    ["ca-mon-1",   "ca-mon-2",   "ca-mon-3"],
    "br-sao":    ["br-sao-1",   "br-sao-2",   "br-sao-3"],
    "eu-gb":     ["eu-gb-1",    "eu-gb-2",    "eu-gb-3"],
    "eu-de":     ["eu-de-1",    "eu-de-2",    "eu-de-3"],
    "eu-es":     ["eu-es-1",    "eu-es-2",    "eu-es-3"],
    "eu-fr2":    ["eu-fr2-1",   "eu-fr2-2",   "eu-fr2-3"],
    "jp-tok":    ["jp-tok-1",   "jp-tok-2",   "jp-tok-3"],
    "jp-osa":    ["jp-osa-1",   "jp-osa-2",   "jp-osa-3"],
    "au-syd":    ["au-syd-1",   "au-syd-2",   "au-syd-3"],
    "in-che":    ["in-che-1"],
    "kr-seo":    ["kr-seo-1",   "kr-seo-2"],
    "mx-qro":    ["mx-qro-1",   "mx-qro-2",   "mx-qro-3"],
}


def get_geography(region: str) -> str:
    return IBM_VPC_REGIONS.get(region, "North America")


def get_valid_datacenters(region: str) -> list[str]:
    return IBM_VPC_DATACENTERS.get(region, [f"{region}-1"])


# ---------------------------------------------------------------------------
# Static Data Domains sheet (174 rows — never changes per project)
# Derived from the jonesmi sample file verbatim.
# ---------------------------------------------------------------------------

_DATA_DOMAINS_HEADERS = [
    "Region", "Data Center", "Subnet access", "Access", "Compute Server Type",
    "Compute Architecture", "Compute Category VS", "Compute Category BM",
    "Feature VS", "Feature BM", "Operating System VS", "Operating System BM",
    "Operating System Version VS", "Operating System Version BM",
    "VPN Type", "Load Balancer Type", "VPN server modes", "IOPS", "Billing Type",
    "Direct Link Type", "Direct Link Version", "Port Metering", "Routing Type",
    "Speed", "Location", "Requirement Type", "Compute Family VS", "Compute Family BM",
]

# Each row: values aligned to _DATA_DOMAINS_HEADERS (None = empty cell)
_DATA_DOMAINS_ROWS = [
    ["au-syd","au-syd-1","Public","Public","Virtual Server","x86","Flex-Balanced","Balanced","{}","Local disk","CentOS","CentOS","ibm-centos-7-9-minimal-amd64-12","ibm-centos-7-9-minimal-amd64-12","Site to Site","Application","Standalone mode",3,"PAYG","DL Connect","Direct Link 2.0","Metered","Local","50 Mbps","US","Zone","bz2e-1x4","bx2-metal-96x384"],
    ["br-sao","au-syd-2","Private","Private","Bare Metal Server","s390x","Flex-Compute","Compute","{High Bandwidth}",None,"CentOS Stream","CentOS Stream","ibm-centos-stream-9-amd64-4","ibm-centos-stream-9-amd64-4","Client to Site","Network","HA mode",5,"1 Yr Reserved","DL Dedicated","Direct Link Classic","Unmetered","Global","100 Mbps","Canada","VPN","bz2-1x4","bx2d-metal-96x384"],
    ["ca-tor","au-syd-3",None,None,None,None,"Flex-Memory","Memory","{High Bandwidth, Instance Storage}",None,"Debian GNU/Linux","Debian GNU/Linux","ibm-centos-stream-8-amd64-4","ibm-debian-11-7-minimal-amd64-2",None,None,None,10,"3 Yr Reserved","DL Exchange",None,None,None,"200 Mbps","Europe","Subnet","bz2e-2x8","cx2-metal-96x192"],
    ["eu-de","br-sao-1",None,None,None,None,"Flex-Nano","High Memory","{Instance Storage}",None,"Fedora CoreOS","Red Hat Enterprise Linux","ibm-debian-12-0-minimal-amd64-1","ibm-redhat-9-2-minimal-amd64-2",None,None,None,None,None,None,None,None,None,"500 Mbps","Asia Pacific","Load Balancer","bz2e-4x16","cx2d-metal-96x192"],
    ["eu-gb","br-sao-2",None,None,None,None,"Balanced",None,None,None,"Red Hat Enterprise Linux","Red Hat Enterprise Linux for SAP","ibm-debian-11-7-minimal-amd64-2","ibm-redhat-9-0-minimal-amd64-4",None,None,None,None,None,None,None,None,None,"1 Gbps","Brazil","Compute","bz2-4x16","mx2-metal-96x768"],
    ["eu-es","br-sao-3",None,None,None,None,"Compute",None,None,None,"Red Hat Enterprise Linux for SAP","SUSE Linux Enterprise Server","ibm-debian-10-13-minimal-amd64-4","ibm-redhat-8-8-minimal-amd64-2",None,None,None,None,None,None,None,None,None,"2 Gbps","Mexico","Data Volume","bz2e-4x16","mx2d-metal-96x768"],
    ["jp-osa","ca-tor-1",None,None,None,None,"Memory",None,None,None,"Rocky Linux","SUSE Linux Enterprise Server for SAP","ibm-fedora-coreos-38-testing-2","ibm-redhat-8-6-minimal-amd64-6",None,None,None,None,None,None,None,None,None,"5 Gbps",None,"Direct Link","bz2e-8x32","bx3-metal-48x256"],
    ["jp-tok","ca-tor-2",None,None,None,None,"GPU",None,None,None,"SUSE Linux Enterprise Server","Ubuntu Linux","ibm-fedora-coreos-38-stable-2","ibm-redhat-9-2-amd64-sap-hana-1",None,None,None,None,None,None,None,None,None,"10 Gbps",None,"File Storage","bz2-8x32","bx3d-metal-48x256"],
    ["us-east","ca-tor-3",None,None,None,None,"High memory",None,None,None,"SUSE Linux Enterprise Server for SAP","VMware vSphere","ibm-redhat-9-2-minimal-amd64-2","ibm-redhat-9-2-amd64-sap-applications-1",None,None,None,None,None,None,None,None,None,None,None,None,"bz2-16x64","bx3-metal-64x256"],
    ["us-south","eu-de-1",None,None,None,None,"Storage optimized",None,None,None,"Ubuntu Linux","Windows Server","ibm-redhat-9-0-minimal-amd64-4","ibm-redhat-9-0-amd64-sap-hana-3",None,None,None,None,None,None,None,None,None,None,None,None,"bz2e-16x64","bx3d-metal-64x256"],
    [None,"eu-de-2",None,None,None,None,None,None,None,None,"Windows Server",None,"ibm-redhat-8-8-minimal-amd64-2","ibm-redhat-9-0-amd64-sap-applications-3",None,None,None,None,None,None,None,None,None,None,None,None,"cz2e-2x4","cx3-metal-48x128"],
    [None,"eu-de-3",None,None,None,None,None,None,None,None,"Windows Server with SQL Server",None,"ibm-redhat-8-6-minimal-amd64-6","ibm-redhat-8-8-amd64-sap-hana-1",None,None,None,None,None,None,None,None,None,None,None,None,"cz2-2x4","cx3d-metal-48x128"],
    [None,"eu-gb-1",None,None,None,None,None,None,None,None,"IBM Z",None,"ibm-redhat-7-9-minimal-amd64-11","ibm-redhat-8-8-amd64-sap-applications-1",None,None,None,None,None,None,None,None,None,None,None,None,"cz2-4x8","cx3-metal-64x128"],
    [None,"eu-gb-2",None,None,None,None,None,None,None,None,"Hyper Protect",None,"ibm-redhat-9-2-amd64-sap-hana-1","ibm-redhat-8-6-amd64-sap-hana-4",None,None,None,None,None,None,None,None,None,None,None,None,"cz2e-4x8","cx3d-metal-64x128"],
    [None,"eu-gb-3",None,None,None,None,None,None,None,None,None,None,"ibm-redhat-9-2-amd64-sap-applications-1","ibm-redhat-8-6-amd64-sap-applications-4",None,None,None,None,None,None,None,None,None,None,None,None,"cz2-8x16","mx3-metal-16x128"],
    [None,"eu-es-1",None,None,None,None,None,None,None,None,None,None,"ibm-redhat-9-0-amd64-sap-hana-3","ibm-redhat-8-4-amd64-sap-hana-8",None,None,None,None,None,None,None,None,None,None,None,None,"cz2e-8x16","mx3d-metal-16x128"],
    [None,"eu-es-2",None,None,None,None,None,None,None,None,None,None,"ibm-redhat-9-0-amd64-sap-applications-3","ibm-redhat-8-4-amd64-sap-applications-8",None,None,None,None,None,None,None,None,None,None,None,None,"cz2e-16x32","mx3-metal-48x512"],
    [None,"eu-es-3",None,None,None,None,None,None,None,None,None,None,"ibm-redhat-8-8-amd64-sap-hana-1","ibm-sles-15-5-amd64-1",None,None,None,None,None,None,None,None,None,None,None,None,"cz2-16x32","mx3d-metal-48x512"],
    [None,"jp-osa-1",None,None,None,None,None,None,None,None,None,None,"ibm-redhat-8-8-amd64-sap-applications-1","ibm-sles-12-5-amd64-6",None,None,None,None,None,None,None,None,None,None,None,None,"mz2e-2x16","mx3-metal-64x512"],
    [None,"jp-osa-2",None,None,None,None,None,None,None,None,None,None,"ibm-redhat-8-6-amd64-sap-hana-4","ibm-sles-15-5-amd64-sap-hana-1",None,None,None,None,None,None,None,None,None,None,None,None,"mz2-2x16","mx3d-metal-64x512"],
    [None,"jp-osa-3",None,None,None,None,None,None,None,None,None,None,"ibm-redhat-8-6-amd64-sap-applications-4","ibm-sles-15-5-amd64-sap-applications-1",None,None,None,None,None,None,None,None,None,None,None,None,"mz2e-4x32","ox2-metal-96x1536"],
    [None,"jp-tok-1",None,None,None,None,None,None,None,None,None,None,"ibm-redhat-8-4-amd64-sap-hana-8","ibm-windows-server-2022-amd64-9",None,None,None,None,None,None,None,None,None,None,None,None,"mz2-4x32","ox2d-metal-96x1536"],
    [None,"jp-tok-2",None,None,None,None,None,None,None,None,None,None,"ibm-redhat-8-4-amd64-sap-applications-8","ibm-windows-server-2019-amd64-11",None,None,None,None,None,None,None,None,None,None,None,None,"mz2e-8x64","ux2d-metal-112x3072"],
    [None,"jp-tok-3",None,None,None,None,None,None,None,None,None,None,"ibm-sles-15-5-amd64-1","ibm-windows-server-2016-amd64-12",None,None,None,None,None,None,None,None,None,None,None,None,"mz2-8x64","vx2d-metal-96x1792"],
    [None,"us-east-1",None,None,None,None,None,None,None,None,None,None,"ibm-sles-12-5-amd64-6","ibm-windows-server-2012-r2-amd64-12",None,None,None,None,None,None,None,None,None,None,None,None,"mz2e-16x128","bx2-48x192"],
    [None,"us-east-2",None,None,None,None,None,None,None,None,None,None,"ibm-sles-15-5-amd64-sap-hana-1","ibm-windows-server-2008-r2-amd64-12",None,None,None,None,None,None,None,None,None,None,None,None,"mz2-16x128","bx2d-48x192"],
    [None,"us-east-3",None,None,None,None,None,None,None,None,None,None,"ibm-sles-15-5-amd64-sap-applications-1",None,None,None,None,None,None,None,None,None,None,None,None,None,"mz2e-32x256","cx2-8x16"],
    [None,"us-south-1",None,None,None,None,None,None,None,None,None,None,"ibm-sles-15-5-amd64-sap-applications-1",None,None,None,None,None,None,None,None,None,None,None,None,None,"mz2-32x256","cx2d-8x16"],
    [None,"us-south-2",None,None,None,None,None,None,None,None,None,None,"ibm-windows-server-2022-amd64-9",None,None,None,None,None,None,None,None,None,None,None,None,None,"ox2-2x16","cx2-16x32"],
    [None,"us-south-3",None,None,None,None,None,None,None,None,None,None,"ibm-windows-server-2019-amd64-11",None,None,None,None,None,None,None,None,None,None,None,None,None,"ox2-4x32","cx2d-16x32"],
    [None,"br-sao-1",None,None,None,None,None,None,None,None,None,None,"ibm-windows-server-2016-amd64-12",None,None,None,None,None,None,None,None,None,None,None,None,None,"ox2-8x64","cx2-32x64"],
    [None,"br-sao-2",None,None,None,None,None,None,None,None,None,None,"ibm-windows-server-2012-r2-amd64-12",None,None,None,None,None,None,None,None,None,None,None,None,None,"ox2-16x128","cx2d-32x64"],
    [None,"br-sao-3",None,None,None,None,None,None,None,None,None,None,"ibm-windows-server-2008-r2-amd64-12",None,None,None,None,None,None,None,None,None,None,None,None,None,"ox2-32x256","cx2-48x96"],
    [None,"ca-tor-1",None,None,None,None,None,None,None,None,None,None,"ibm-ubuntu-22-04-6-minimal-amd64-2",None,None,None,None,None,None,None,None,None,None,None,None,None,"ox2d-2x16","cx2d-48x96"],
    [None,"ca-tor-2",None,None,None,None,None,None,None,None,None,None,"ibm-ubuntu-20-04-6-minimal-amd64-4",None,None,None,None,None,None,None,None,None,None,None,None,None,"ox2d-4x32","cx2-64x128"],
    [None,"ca-tor-3",None,None,None,None,None,None,None,None,None,None,"ibm-ubuntu-18-04-6-minimal-amd64-4",None,None,None,None,None,None,None,None,None,None,None,None,None,"ox2d-8x64","cx2d-64x128"],
    [None,"eu-fr2-1",None,None,None,None,None,None,None,None,None,None,"ibm-rocky-linux-9-2-minimal-amd64-1",None,None,None,None,None,None,None,None,None,None,None,None,None,"ox2d-16x128","cx2-96x192"],
    [None,"eu-fr2-2",None,None,None,None,None,None,None,None,None,None,"ibm-rocky-linux-8-8-minimal-amd64-2",None,None,None,None,None,None,None,None,None,None,None,None,None,"ox2d-32x256","cx2d-96x192"],
    [None,None,None,None,None,None,None,None,None,None,None,None,"ibm-debian-12-0-minimal-amd64-1",None,None,None,None,None,None,None,None,None,None,None,None,None,"bxf-2x8","mx2-2x16"],
    [None,None,None,None,None,None,None,None,None,None,None,None,"ibm-debian-11-7-minimal-amd64-2",None,None,None,None,None,None,None,None,None,None,None,None,None,"bxf-4x16","mx2d-2x16"],
    [None,None,None,None,None,None,None,None,None,None,None,None,"ibm-debian-10-13-minimal-amd64-4",None,None,None,None,None,None,None,None,None,None,None,None,None,"bxf-8x32","mx2-4x32"],
    [None,None,None,None,None,None,None,None,None,None,None,None,"ibm-centos-7-9-minimal-amd64-12",None,None,None,None,None,None,None,None,None,None,None,None,None,"bxf-16x64","mx2d-4x32"],
    [None,None,None,None,None,None,None,None,None,None,None,None,"ibm-centos-stream-9-amd64-4",None,None,None,None,None,None,None,None,None,None,None,None,None,"bxf-32x128","mx2-8x64"],
    [None,None,None,None,None,None,None,None,None,None,None,None,"ibm-centos-stream-8-amd64-4",None,None,None,None,None,None,None,None,None,None,None,None,None,"bxf-48x192","mx2d-8x64"],
    [None,None,None,None,None,None,None,None,None,None,None,None,"ibm-fedora-coreos-38-stable-2",None,None,None,None,None,None,None,None,None,None,None,None,None,"bxf-64x256","mx2-16x128"],
    [None,None,None,None,None,None,None,None,None,None,None,None,"ibm-fedora-coreos-38-testing-2",None,None,None,None,None,None,None,None,None,None,None,None,None,"bxf-96x384","mx2d-16x128"],
    [None,None,None,None,None,None,None,None,None,None,None,None,"ibm-redhat-9-2-minimal-amd64-2",None,None,None,None,None,None,None,None,None,None,None,None,None,"cxf-2x4","mx2-32x256"],
    [None,None,None,None,None,None,None,None,None,None,None,None,"ibm-redhat-9-0-minimal-amd64-4",None,None,None,None,None,None,None,None,None,None,None,None,None,"cxf-4x8","mx2d-32x256"],
    [None,None,None,None,None,None,None,None,None,None,None,None,"ibm-redhat-8-8-minimal-amd64-2",None,None,None,None,None,None,None,None,None,None,None,None,None,"cxf-8x16","mx2-48x384"],
    [None,None,None,None,None,None,None,None,None,None,None,None,"ibm-redhat-8-6-minimal-amd64-6",None,None,None,None,None,None,None,None,None,None,None,None,None,"cxf-16x32","mx2d-48x384"],
    [None,None,None,None,None,None,None,None,None,None,None,None,"ibm-redhat-7-9-minimal-amd64-11",None,None,None,None,None,None,None,None,None,None,None,None,None,"cxf-24x48","mx2-64x512"],
    [None,None,None,None,None,None,None,None,None,None,None,None,"ibm-redhat-8-8-amd64-sap-hana-1",None,None,None,None,None,None,None,None,None,None,None,None,None,"cxf-32x64","mx2d-64x512"],
    [None,None,None,None,None,None,None,None,None,None,None,None,"ibm-redhat-8-6-amd64-sap-hana-4",None,None,None,None,None,None,None,None,None,None,None,None,None,"cxf-48x96","mx2-96x768"],
    [None,None,None,None,None,None,None,None,None,None,None,None,"ibm-redhat-8-4-amd64-sap-hana-8",None,None,None,None,None,None,None,None,None,None,None,None,None,"cxf-64x128","mx2d-96x768"],
    [None,None,None,None,None,None,None,None,None,None,None,None,"ibm-redhat-9-2-amd64-sap-hana-1",None,None,None,None,None,None,None,None,None,None,None,None,None,"cxf-96x192","gx2-8x64x1v100"],
    [None,None,None,None,None,None,None,None,None,None,None,None,"ibm-redhat-9-0-amd64-sap-hana-3",None,None,None,None,None,None,None,None,None,None,None,None,None,"mxf-2x16","gx2-16x128x1v100"],
    [None,None,None,None,None,None,None,None,None,None,None,None,"ibm-redhat-8-8-amd64-sap-applications-1",None,None,None,None,None,None,None,None,None,None,None,None,None,"mxf-4x32","gx2-32x256x2v100"],
    [None,None,None,None,None,None,None,None,None,None,None,None,"ibm-redhat-8-6-amd64-sap-applications-4",None,None,None,None,None,None,None,None,None,None,None,None,None,"mxf-8x64","gx2-80x1280x8v100"],
    [None,None,None,None,None,None,None,None,None,None,None,None,"ibm-redhat-8-4-amd64-sap-applications-8",None,None,None,None,None,None,None,None,None,None,None,None,None,"mxf-16x128","vx2d-4x56"],
    [None,None,None,None,None,None,None,None,None,None,None,None,"ibm-redhat-9-2-amd64-sap-applications-1",None,None,None,None,None,None,None,None,None,None,None,None,None,"mxf-24x192","vx2d-8x112"],
    [None,None,None,None,None,None,None,None,None,None,None,None,"ibm-redhat-9-0-amd64-sap-applications-3",None,None,None,None,None,None,None,None,None,None,None,None,None,"mxf-32x256","vx2d-16x224"],
    [None,None,None,None,None,None,None,None,None,None,None,None,"ibm-sles-15-5-amd64-1",None,None,None,None,None,None,None,None,None,None,None,None,None,"mxf-48x384","vx2d-28x392"],
    [None,None,None,None,None,None,None,None,None,None,None,None,"ibm-sles-12-5-amd64-6",None,None,None,None,None,None,None,None,None,None,None,None,None,"mxf-64x512","vx2d-44x616"],
    [None,None,None,None,None,None,None,None,None,None,None,None,"ibm-sles-15-5-amd64-sap-hana-1",None,None,None,None,None,None,None,None,None,None,None,None,None,"mxf-96x768","vx2d-56x784"],
    [None,None,None,None,None,None,None,None,None,None,None,None,"ibm-sles-15-5-amd64-sap-applications-1",None,None,None,None,None,None,None,None,None,None,None,None,None,None,"vx2d-88x1232"],
    [None,None,None,None,None,None,None,None,None,None,None,None,"ibm-ubuntu-22-04-6-minimal-amd64-2",None,None,None,None,None,None,None,None,None,None,None,None,None,None,"vx2d-144x2016"],
    [None,None,None,None,None,None,None,None,None,None,None,None,"ibm-ubuntu-20-04-6-minimal-amd64-4",None,None,None,None,None,None,None,None,None,None,None,None,None,None,"vx2d-176x2464"],
    [None,None,None,None,None,None,None,None,None,None,None,None,"ibm-ubuntu-18-04-6-minimal-amd64-4",None,None,None,None,None,None,None,None,None,None,None,None,None,None,"ux2d-8x224"],
    [None,None,None,None,None,None,None,None,None,None,None,None,"ibm-rocky-linux-9-2-minimal-amd64-1",None,None,None,None,None,None,None,None,None,None,None,None,None,None,"ux2d-16x448"],
    [None,None,None,None,None,None,None,None,None,None,None,None,"ibm-rocky-linux-8-8-minimal-amd64-2",None,None,None,None,None,None,None,None,None,None,None,None,None,None,"ux2d-36x1008"],
    [None,None,None,None,None,None,None,None,None,None,None,None,"ibm-windows-server-2022-amd64-9",None,None,None,None,None,None,None,None,None,None,None,None,None,None,"ux2d-52x1456"],
    [None,None,None,None,None,None,None,None,None,None,None,None,"ibm-windows-server-2019-amd64-11",None,None,None,None,None,None,None,None,None,None,None,None,None,None,"ux2d-72x2016"],
    [None,None,None,None,None,None,None,None,None,None,None,None,"ibm-windows-server-2016-amd64-12",None,None,None,None,None,None,None,None,None,None,None,None,None,None,"ux2d-100x2800"],
    [None,None,None,None,None,None,None,None,None,None,None,None,"ibm-windows-server-2012-r2-amd64-12",None,None,None,None,None,None,None,None,None,None,None,None,None,None,"bz2e-1x4"],
    [None,None,None,None,None,None,None,None,None,None,None,None,"ibm-windows-server-2008-r2-amd64-12",None,None,None,None,None,None,None,None,None,None,None,None,None,None,"bz2-1x4"],
]

# Pad all rows to 28 columns (some rows have fewer entries)
_DATA_DOMAINS_ROWS = [
    row + [None] * (28 - len(row)) for row in _DATA_DOMAINS_ROWS
]


# ---------------------------------------------------------------------------
# Workbook styling helpers
# ---------------------------------------------------------------------------

_THIN = Side(style="thin")
_ALL_BORDERS = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)
_HEADER_FILL = PatternFill("solid", fgColor="D3D3D3")
_HEADER_FONT = Font(bold=True)
_ISSUE_FILL  = PatternFill("solid", fgColor="FFF2CC")   # light yellow — flags rows with issues


def _write_header(ws: Any, headers: list[str]) -> None:
    ws.append(headers)
    for col_idx, _ in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.font = _HEADER_FONT
        cell.fill = _HEADER_FILL
        cell.border = _ALL_BORDERS
        cell.alignment = Alignment(wrap_text=True)


def _auto_size(ws: Any, headers: list[str]) -> None:
    for col_idx, header in enumerate(headers, 1):
        max_len = len(header)
        for row in ws.iter_rows(min_row=2, min_col=col_idx, max_col=col_idx):
            for cell in row:
                if cell.value is not None:
                    max_len = max(max_len, len(str(cell.value)))
        ws.column_dimensions[ws.cell(row=1, column=col_idx).column_letter].width = min(max_len + 2, 40)


# ---------------------------------------------------------------------------
# Project Settings column headers (47 columns — exact from sample)
# ---------------------------------------------------------------------------

PS_HEADERS = [
    "Issues", "Compute name", "Compute Category VS", "Compute Family VS",
    "Number of instances", "Billing Type", "Boot Volume Size (GB)", "IOPS",
    "Data Volume Size (GB)", "Requirement Type", "VPC name", "Geography",
    "Region", "Data Center", "Expected Internet Traffic (GB)", "VPN Type",
    "Load Balancer Type", "Expected hours per month", "VPN server modes",
    "Subnet name", "Subnet purpose", "Subnet access", "Access",
    "Expected GB per month", "Compute Architecture", "Confidential Computing",
    "Compute Server Type", "Feature BM", "Compute Category BM", "Compute Family BM",
    "Operating System BM", "Operating System Version BM", "Feature VS",
    "Operating System VS", "Operating System Version VS", "Direct Link Name",
    "Direct Link Type", "Direct Link Version", "Port Metering", "Routing Type",
    "Speed", "Location", "Transfer Charges", "High Availability",
    "File storage description", "File storage size", "File storage Max IOPS (Gbs)",
]

# Column index map (1-based)
_PS = {h: i for i, h in enumerate(PS_HEADERS, 1)}


def _ps_row(n: int) -> list[Any]:
    """Return a blank 47-element list for one Project Settings row."""
    return [None] * n


def _set(row: list, header: str, val: Any) -> None:
    """Set a value by header name in a PS row (mutates in place)."""
    idx = _PS[header] - 1   # 0-based
    row[idx] = val


# ---------------------------------------------------------------------------
# Main generator
# ---------------------------------------------------------------------------

def generate_vpc_calculator_xlsx(
    records: list[dict],
    project_name: str,
    vpc_region: str = "us-south",
    vpc_datacenter: str = "us-south-1",
) -> bytes:
    """Generate a 3-sheet IBM Cloud VPC Calculator workbook.

    Args:
        records: List of enriched record dicts from _fetch_enriched_records().
                 Each has keys: normalized_data, server_type, is_excluded.
        project_name: Used in the workbook title / filename.
        vpc_region: IBM VPC target region (e.g. "us-south").
        vpc_datacenter: IBM VPC availability zone (e.g. "us-south-1").

    Returns:
        Raw bytes of the generated .xlsx workbook.
    """
    geography = get_geography(vpc_region)

    # Filter: x86 non-excluded only (PowerVS goes to a separate export)
    active = [
        r for r in records
        if not r.get("is_excluded")
        and r.get("server_type", "vm") != "powervs"
        and r.get("normalized_data")
    ]

    wb = Workbook()

    # -------------------------------------------------------------------
    # Sheet 1: Project Settings
    # -------------------------------------------------------------------
    ps_ws = wb.active
    ps_ws.title = "Project Settings"
    _write_header(ps_ws, PS_HEADERS)

    # Zone row
    zone_row = _ps_row(len(PS_HEADERS))
    _set(zone_row, "Requirement Type", "Zone")
    _set(zone_row, "VPC name",         "Default VPC")
    _set(zone_row, "Geography",        geography)
    _set(zone_row, "Region",           vpc_region)
    _set(zone_row, "Data Center",      vpc_datacenter)
    ps_ws.append(zone_row)

    # Subnet row
    sub_row = _ps_row(len(PS_HEADERS))
    _set(sub_row, "Requirement Type", "Subnet")
    _set(sub_row, "Geography",        geography)
    _set(sub_row, "Region",           vpc_region)
    _set(sub_row, "Data Center",      vpc_datacenter)
    _set(sub_row, "Subnet name",      "Default VPC")
    _set(sub_row, "Subnet access",    "Private")
    ps_ws.append(sub_row)

    # Per-VM: Compute + Data Volume rows
    exception_rows: list[list[Any]] = []

    for rec in active:
        nd = rec["normalized_data"]
        vinfo = nd.get("vinfo") or {}
        server_type = rec.get("server_type", "vm")

        vm_name    = vinfo.get("vm_name", "unknown")
        cpus       = int(vinfo.get("num_cpus") or vinfo.get("cpus") or 1)
        mem_mb     = int(vinfo.get("memory_mb") or vinfo.get("memory") or 4096)
        mem_gb     = max(1, round(mem_mb / 1024))
        prov_mb    = int(vinfo.get("provisioned_mb") or mem_mb)
        prov_gb    = max(1, round(prov_mb / 1024))
        os_config  = vinfo.get("os_config") or vinfo.get("os_vmware_tools") or ""
        is_bm      = server_type == "bare_metal"

        _, os_image = _map_os_to_image(os_config)
        category, family, no_profile = _select_vpc_profile(cpus, mem_gb)

        # Issues column: always flag boot_increased (IBM VPC boot < on-prem provisioned)
        issues_parts = ["boot_increased"]
        if no_profile:
            issues_parts.append("no_matching_profile")
        issues_str = ",".join(issues_parts)

        # Compute row
        cmp_row = _ps_row(len(PS_HEADERS))
        _set(cmp_row, "Issues",                    issues_str)
        _set(cmp_row, "Compute name",              vm_name)
        _set(cmp_row, "Number of instances",       1)
        _set(cmp_row, "Billing Type",              "PAYG")
        _set(cmp_row, "Boot Volume Size (GB)",     10)
        _set(cmp_row, "IOPS",                      3)
        _set(cmp_row, "Requirement Type",          "Compute")
        _set(cmp_row, "Data Center",               vpc_datacenter)
        _set(cmp_row, "Compute Architecture",      "x86")
        _set(cmp_row, "Confidential Computing",    "No")
        _set(cmp_row, "Compute Server Type",       "Bare Metal Server" if is_bm else "Virtual Server")
        _set(cmp_row, "Feature VS",                "{}")
        _set(cmp_row, "Operating System Version VS", os_image)
        if not no_profile:
            _set(cmp_row, "Compute Category VS",  category)
            _set(cmp_row, "Compute Family VS",    family)

        ps_ws.append(cmp_row)

        # If no matching profile → also write to Exceptions sheet
        if no_profile:
            exception_rows.append(list(cmp_row))  # copy

        # Data Volume row (one per VM — provisioned disk size)
        dv_row = _ps_row(len(PS_HEADERS))
        _set(dv_row, "IOPS",                  3)
        _set(dv_row, "Data Volume Size (GB)", prov_gb)
        _set(dv_row, "Requirement Type",      "Data Volume")
        _set(dv_row, "Geography",             geography)
        _set(dv_row, "Region",                vpc_region)
        _set(dv_row, "Data Center",           vpc_datacenter)
        ps_ws.append(dv_row)

    # Style all data rows
    for row_cells in ps_ws.iter_rows(min_row=2):
        issues_val = row_cells[0].value  # column A = Issues
        fill = _ISSUE_FILL if issues_val else None
        for cell in row_cells:
            cell.border = _ALL_BORDERS
            cell.alignment = Alignment(wrap_text=False)
            if fill:
                cell.fill = fill

    _auto_size(ps_ws, PS_HEADERS)
    ps_ws.freeze_panes = "A2"

    # -------------------------------------------------------------------
    # Sheet 2: Exceptions (same layout as Project Settings)
    # -------------------------------------------------------------------
    ex_ws = wb.create_sheet("Exceptions")
    _write_header(ex_ws, PS_HEADERS)

    # Zone + Subnet header rows (same as Project Settings)
    ex_ws.append(list(zone_row))
    ex_ws.append(list(sub_row))

    for ex_row in exception_rows:
        ex_ws.append(ex_row)
        # Also add its data volume row for completeness
        dv_row2 = _ps_row(len(PS_HEADERS))
        _set(dv_row2, "IOPS",                  3)
        # Recover prov_gb from the main sheet — find by Compute name
        vm_name_ex = ex_row[_PS["Compute name"] - 1]
        prov_gb_ex = 100  # fallback
        for rec in active:
            nd = rec["normalized_data"]
            vinfo = nd.get("vinfo") or {}
            if vinfo.get("vm_name") == vm_name_ex:
                pm = int(vinfo.get("provisioned_mb") or vinfo.get("memory_mb") or 102400)
                prov_gb_ex = max(1, round(pm / 1024))
                break
        _set(dv_row2, "Data Volume Size (GB)", prov_gb_ex)
        _set(dv_row2, "Requirement Type",      "Data Volume")
        _set(dv_row2, "Geography",             geography)
        _set(dv_row2, "Region",                vpc_region)
        _set(dv_row2, "Data Center",           vpc_datacenter)
        ex_ws.append(dv_row2)

    for row_cells in ex_ws.iter_rows(min_row=2):
        for cell in row_cells:
            cell.border = _ALL_BORDERS
            cell.alignment = Alignment(wrap_text=False)

    _auto_size(ex_ws, PS_HEADERS)
    ex_ws.freeze_panes = "A2"

    # -------------------------------------------------------------------
    # Sheet 3: Data Domains (static reference table)
    # -------------------------------------------------------------------
    dd_ws = wb.create_sheet("Data Domains")
    _write_header(dd_ws, _DATA_DOMAINS_HEADERS)

    for dd_row in _DATA_DOMAINS_ROWS:
        dd_ws.append(dd_row)
        for cell in dd_ws[dd_ws.max_row]:
            cell.border = _ALL_BORDERS
            cell.alignment = Alignment(wrap_text=False)

    _auto_size(dd_ws, _DATA_DOMAINS_HEADERS)
    dd_ws.freeze_panes = "A2"

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()
