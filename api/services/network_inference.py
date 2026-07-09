"""Network inference utilities — generate consistent network defaults for a project.

These defaults are applied as post-processing after the AI normalization step.
Every injected value is recorded as an assumption so it appears in the Assumptions Report.
"""
from __future__ import annotations


# IBM Cloud / on-prem common DNS servers used as defaults
_DEFAULT_DNS_PRIMARY   = "8.8.8.8"
_DEFAULT_DNS_SECONDARY = "8.8.4.4"
_DEFAULT_VSWITCH       = "vSwitch0"
_DEFAULT_PORTGROUP     = "VM Network"
_DEFAULT_VLAN          = "0"
_DEFAULT_SECURITY_GROUP = "default-sg"


def get_default_network_config(vm_name: str, index: int) -> dict:
    """Generate default network config for a VM that has no IP info.

    Assigns IPs sequentially from the 10.0.x.x range based on the
    record index so every VM in a project gets a distinct placeholder IP.
    """
    subnet_octet = (index // 253) + 1          # 10.0.1.x, 10.0.2.x …
    host_octet   = (index % 253) + 2           # .2 – .254 (skip .1 = gateway)

    ipv4         = f"10.0.{subnet_octet}.{host_octet}"
    gateway      = f"10.0.{subnet_octet}.1"
    cidr         = f"10.0.{subnet_octet}.0/24"
    broadcast    = f"10.0.{subnet_octet}.255"

    return {
        "ipv4_address":     ipv4,
        "subnet_mask":      "255.255.255.0",
        "cidr":             cidr,
        "gateway":          gateway,
        "broadcast":        broadcast,
        "dns_primary":      _DEFAULT_DNS_PRIMARY,
        "dns_secondary":    _DEFAULT_DNS_SECONDARY,
        "network":          _DEFAULT_PORTGROUP,
        "switch":           _DEFAULT_VSWITCH,
        "vlan_id":          _DEFAULT_VLAN,
        "security_group":   _DEFAULT_SECURITY_GROUP,
    }


def get_network_assumptions(vm_name: str, index: int, provided_ip: str | None) -> list[dict]:
    """Return assumption records for all network fields that were defaulted.

    Call this after get_default_network_config when the customer did not supply
    network information — the returned list is appended to the record's assumptions.
    """
    cfg   = get_default_network_config(vm_name, index)
    ipv4  = cfg["ipv4_address"]
    gw    = cfg["gateway"]
    cidr  = cfg["cidr"]

    assumptions = []

    if not provided_ip:
        assumptions.append({
            "field_name":    "vnetwork/ipv4_address",
            "assumed_value": ipv4,
            "original_value": None,
            "reasoning": (
                f"No IP address supplied for '{vm_name}'. "
                f"Assigned sequential placeholder {ipv4} from the 10.0.0.0/8 "
                "range. Must be replaced with the actual customer IP before production use."
            ),
            "confidence": "low",
        })

    assumptions += [
        {
            "field_name":    "vnetwork/gateway",
            "assumed_value": gw,
            "original_value": None,
            "reasoning": (
                f"Default gateway {gw} (first host in {cidr}) applied. "
                "Replace with actual gateway from customer network documentation."
            ),
            "confidence": "low",
        },
        {
            "field_name":    "vnetwork/subnet_cidr",
            "assumed_value": cidr,
            "original_value": None,
            "reasoning": (
                f"Default /24 subnet {cidr} applied. No subnet information "
                "was provided in the customer spreadsheet."
            ),
            "confidence": "low",
        },
        {
            "field_name":    "vnetwork/dns",
            "assumed_value": f"{_DEFAULT_DNS_PRIMARY}, {_DEFAULT_DNS_SECONDARY}",
            "original_value": None,
            "reasoning": (
                "Public Google DNS servers used as placeholder. Replace with "
                "actual customer DNS resolvers."
            ),
            "confidence": "low",
        },
        {
            "field_name":    "vnetwork/security_group",
            "assumed_value": _DEFAULT_SECURITY_GROUP,
            "original_value": None,
            "reasoning": (
                "IBM Cloud default security group applied. Customer must review "
                "and assign correct security group policies for each server."
            ),
            "confidence": "low",
        },
        {
            "field_name":    "vnetwork/vswitch",
            "assumed_value": _DEFAULT_VSWITCH,
            "original_value": None,
            "reasoning": (
                f"Default vSwitch '{_DEFAULT_VSWITCH}' applied. "
                "Adjust to match the customer's vSphere network topology."
            ),
            "confidence": "low",
        },
    ]

    return assumptions


def infer_server_type(raw_data: dict) -> str:
    """Detect if a server is a VM or bare metal from field names and values.

    Returns "vm" or "bare_metal".
    """
    combined = " ".join(
        str(v) for v in list(raw_data.keys()) + list(raw_data.values()) if v is not None
    ).lower()

    bare_metal_keywords = {"physical", "bare metal", "baremetal", "bare_metal", " bm ", "bm-"}
    vmware_keywords     = {"vmware", "vsphere", "esxi", "vm ", "virtual machine", "vmare"}

    for kw in bare_metal_keywords:
        if kw in combined:
            return "bare_metal"

    for kw in vmware_keywords:
        if kw in combined:
            return "vm"

    return "vm"
