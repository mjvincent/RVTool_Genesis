"""Unit tests for PowerVS disk-clamping bypass in _sanitize_numeric_fields.

Verifies that the IBM Cloud VPC 100 GB / 250 GB boot volume constraints are
applied to x86 records but NOT to PowerVS (AIX / IBM i / Linux-on-Power)
records — which must pass the customer's raw disk size through unchanged.
"""
from __future__ import annotations

import pytest

from services.ai_normalizer import _sanitize_numeric_fields, _IBM_VPC_BOOT_MIN_MB, _IBM_VPC_BOOT_MAX_MB


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MIN = _IBM_VPC_BOOT_MIN_MB   # 102400 MB (100 GB)
_MAX = _IBM_VPC_BOOT_MAX_MB   # 256000 MB (250 GB)


def _make_result(server_type: str, os_config: str, provisioned_mb: int) -> dict:
    """Build a minimal normalizer result dict suitable for _sanitize_numeric_fields."""
    return {
        "server_type": server_type,
        "vinfo": {
            "vm_name":        "test-server",
            "cpus":           4,
            "memory_mb":      8192,
            "provisioned_mb": provisioned_mb,
            "in_use_mb":      round(provisioned_mb * 0.6),
            "os_config":      os_config,
            "os_vmware_tools": os_config,
            "template":       "FALSE",
            "nics":           1,
            "disks":          1,
        },
        "vnetwork":   [],
        "vpartition": [],
        "assumptions": [],
    }


def _run(result: dict) -> dict:
    """Run _sanitize_numeric_fields and return the mutated result."""
    result["_raw_data"] = {}   # required stub — removed by caller in production
    out = _sanitize_numeric_fields(result)
    out.pop("_raw_data", None)
    return out


# ---------------------------------------------------------------------------
# x86 records — clamping MUST apply
# ---------------------------------------------------------------------------

class TestX86DiskClamping:
    """The 100 GB min / 250 GB max boot volume rules apply to x86 VSIs."""

    def test_x86_below_minimum_clamped_up(self):
        r = _make_result("vm", "Windows Server 2019", provisioned_mb=10 * 1024)  # 10 GB
        out = _run(r)
        assert out["vinfo"]["provisioned_mb"] == _MIN, "x86 disk below 100 GB should be raised to 100 GB"

    def test_x86_above_maximum_clamped_down(self):
        r = _make_result("vm", "Red Hat Enterprise Linux 8", provisioned_mb=500 * 1024)  # 500 GB
        out = _run(r)
        assert out["vinfo"]["provisioned_mb"] == _MAX, "x86 disk above 250 GB should be clamped to 250 GB"

    def test_x86_within_range_unchanged(self):
        prov = 128 * 1024  # 128 GB — within bounds
        r = _make_result("vm", "Ubuntu 22.04", provisioned_mb=prov)
        out = _run(r)
        assert out["vinfo"]["provisioned_mb"] == prov, "x86 disk in range should be unchanged"

    def test_x86_clamp_up_generates_assumption(self):
        r = _make_result("vm", "CentOS 7", provisioned_mb=50 * 1024)
        out = _run(r)
        clamped_assumptions = [
            a for a in out["assumptions"]
            if a.get("field_name") == "vinfo/provisioned_mb"
        ]
        assert len(clamped_assumptions) == 1, "Clamping should produce one assumption"
        assert "100 GB" in clamped_assumptions[0]["reasoning"]

    def test_x86_clamp_down_generates_assumption(self):
        r = _make_result("vm", "Windows Server 2022", provisioned_mb=600 * 1024)
        out = _run(r)
        clamped_assumptions = [
            a for a in out["assumptions"]
            if a.get("field_name") == "vinfo/provisioned_mb"
        ]
        assert len(clamped_assumptions) == 1
        assert "250 GB" in clamped_assumptions[0]["reasoning"]

    def test_x86_total_disk_mb_set_to_preclamped_value(self):
        """total_disk_mb must hold the customer's original value even after clamping."""
        original_mb = 500 * 1024  # 500 GB — will be clamped to 250 GB
        r = _make_result("vm", "Red Hat 8", provisioned_mb=original_mb)
        out = _run(r)
        assert out["vinfo"]["total_disk_mb"] == original_mb, \
            "total_disk_mb should preserve the pre-clamp customer value"


# ---------------------------------------------------------------------------
# PowerVS records — clamping must NOT apply
# ---------------------------------------------------------------------------

class TestPowerVSDiskPassthrough:
    """No 100 GB / 250 GB clamping for PowerVS (AIX / IBM i / Linux-on-Power)."""

    def test_aix_small_disk_not_clamped(self):
        """AIX server with 10 GB disk — customer value passes through unchanged."""
        prov = 10 * 1024  # 10 GB — below x86 minimum, but valid for PowerVS
        r = _make_result("powervs", "AIX 7.3", provisioned_mb=prov)
        out = _run(r)
        assert out["vinfo"]["provisioned_mb"] == prov, \
            "PowerVS AIX disk should NOT be raised to 100 GB"

    def test_aix_large_disk_not_clamped(self):
        """AIX server with 2 TB disk — customer value passes through unchanged."""
        prov = 2048 * 1024  # 2 TB — well above x86 maximum
        r = _make_result("powervs", "AIX 7.2", provisioned_mb=prov)
        out = _run(r)
        assert out["vinfo"]["provisioned_mb"] == prov, \
            "PowerVS AIX disk should NOT be capped at 250 GB"

    def test_ibm_i_small_disk_not_clamped(self):
        prov = 20 * 1024  # 20 GB
        r = _make_result("powervs", "IBM i 7.5", provisioned_mb=prov)
        out = _run(r)
        assert out["vinfo"]["provisioned_mb"] == prov

    def test_ibm_i_large_disk_not_clamped(self):
        prov = 14000 * 1024  # ~14 TB — real IBM i production system
        r = _make_result("powervs", "IBM i 7.4", provisioned_mb=prov)
        out = _run(r)
        assert out["vinfo"]["provisioned_mb"] == prov

    def test_aix_no_clamp_assumption_generated(self):
        """No boot-volume clamping assumption should be added for PowerVS records."""
        prov = 5 * 1024  # 5 GB — would trigger x86 up-clamp
        r = _make_result("powervs", "AIX 7.1", provisioned_mb=prov)
        out = _run(r)
        boot_clamp_assumptions = [
            a for a in out["assumptions"]
            if a.get("field_name") == "vinfo/provisioned_mb"
            and ("100 GB" in (a.get("reasoning") or "") or "250 GB" in (a.get("reasoning") or ""))
        ]
        assert len(boot_clamp_assumptions) == 0, \
            "No boot-volume clamping assumption should appear for PowerVS records"

    def test_powervs_total_disk_mb_equals_provisioned(self):
        """For PowerVS, total_disk_mb should equal the raw provisioned_mb (no clamping occurred)."""
        prov = 8 * 1024  # 8 GB
        r = _make_result("powervs", "AIX 7.3", provisioned_mb=prov)
        out = _run(r)
        assert out["vinfo"]["total_disk_mb"] == prov
        assert out["vinfo"]["provisioned_mb"] == prov

    def test_os_config_powervs_detection_bypasses_clamp(self):
        """server_type='vm' but OS is AIX — the os_config guard should still bypass clamping."""
        prov = 8 * 1024  # 8 GB — below x86 minimum
        # LLM returned the wrong server_type but correct OS — post-processor will fix it
        r = _make_result("vm", "AIX 7.3", provisioned_mb=prov)
        out = _run(r)
        assert out["vinfo"]["provisioned_mb"] == prov, \
            "AIX os_config should bypass disk clamping regardless of server_type"

    def test_linux_on_power_sap_not_clamped(self):
        """SAP Red Hat on Power is a PowerVS OS — disk should pass through unchanged."""
        prov = 30 * 1024  # 30 GB
        r = _make_result("powervs", "SAP Red Hat 8.6", provisioned_mb=prov)
        out = _run(r)
        assert out["vinfo"]["provisioned_mb"] == prov
