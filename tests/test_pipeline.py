"""Integration tests for the RVTool Genesis pipeline.

Tests 1-6 and 8 call the live API at http://localhost:8001.
Test 7 exercises the generator + validator directly without any HTTP or Claude calls.

Run from inside the api container (or with PYTHONPATH=api from project root):
    pytest tests/ -v
"""
from __future__ import annotations

import sys
import os
from pathlib import Path

import httpx
import pytest

# ---------------------------------------------------------------------------
# Ensure api/ package is importable whether running:
#   - inside the container at /app (PYTHONPATH already set via entrypoint), OR
#   - from the host project root with PYTHONPATH=api
# ---------------------------------------------------------------------------
_CONTAINER_APP_DIR = Path("/app")
_HOST_API_DIR = Path(__file__).parent.parent / "api"

for _candidate in (_CONTAINER_APP_DIR, _HOST_API_DIR):
    if _candidate.exists() and str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

# Samples directory — project root / Samples
_SAMPLES_DIR = Path(__file__).parent.parent / "Samples"
_SAMPLE_FILE = _SAMPLES_DIR / "SizingWorkshop-RVTools.xlsx"


# ---------------------------------------------------------------------------
# Test 1 — Health check
# ---------------------------------------------------------------------------

def test_health(base_url: str) -> None:
    """GET /api/health should return {"status": "ok"}."""
    resp = httpx.get(f"{base_url}/api/health", timeout=10)
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") == "ok"


# ---------------------------------------------------------------------------
# Test 2 — Create project
# ---------------------------------------------------------------------------

def test_create_project(test_project: dict) -> None:
    """The test_project fixture should yield a project with id, name, timestamps."""
    assert "id" in test_project
    assert test_project["name"] == "Test Project (auto)"
    assert "created_at" in test_project
    assert "updated_at" in test_project


# ---------------------------------------------------------------------------
# Test 3 — Upload sample file
# ---------------------------------------------------------------------------

def test_upload_sample_file(base_url: str, test_project: dict) -> None:
    """POST /api/projects/{id}/uploads with the sample xlsx should parse rows."""
    project_id = test_project["id"]

    if not _SAMPLE_FILE.exists():
        pytest.skip(f"Sample file not found at {_SAMPLE_FILE}")

    with open(_SAMPLE_FILE, "rb") as fh:
        resp = httpx.post(
            f"{base_url}/api/projects/{project_id}/uploads",
            files={"file": ("SizingWorkshop-RVTools.xlsx", fh, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            timeout=30,
        )

    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["status"] == "complete"
    assert data["row_count"] is not None
    assert data["row_count"] > 0


# ---------------------------------------------------------------------------
# Test 4 — Check records parsed
# ---------------------------------------------------------------------------

def test_records_parsed(base_url: str, test_project: dict) -> None:
    """After upload, GET /api/projects/{id}/records returns records with raw_data."""
    project_id = test_project["id"]

    if not _SAMPLE_FILE.exists():
        pytest.skip(f"Sample file not found at {_SAMPLE_FILE}")

    # Upload first
    with open(_SAMPLE_FILE, "rb") as fh:
        upload_resp = httpx.post(
            f"{base_url}/api/projects/{project_id}/uploads",
            files={"file": ("SizingWorkshop-RVTools.xlsx", fh, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            timeout=30,
        )
    assert upload_resp.status_code == 201

    resp = httpx.get(f"{base_url}/api/projects/{project_id}/records", timeout=10)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] > 0

    first_record = data["records"][0]
    assert first_record["raw_data"] is not None
    assert first_record["normalized_data"] is None


# ---------------------------------------------------------------------------
# Test 5 — Processing status before processing
# ---------------------------------------------------------------------------

def test_processing_status_before_process(base_url: str, test_project: dict) -> None:
    """After upload, processing status should show pending > 0 and is_complete False."""
    project_id = test_project["id"]

    if not _SAMPLE_FILE.exists():
        pytest.skip(f"Sample file not found at {_SAMPLE_FILE}")

    # Upload first
    with open(_SAMPLE_FILE, "rb") as fh:
        upload_resp = httpx.post(
            f"{base_url}/api/projects/{project_id}/uploads",
            files={"file": ("SizingWorkshop-RVTools.xlsx", fh, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            timeout=30,
        )
    assert upload_resp.status_code == 201

    resp = httpx.get(f"{base_url}/api/projects/{project_id}/processing-status", timeout=10)
    assert resp.status_code == 200
    status = resp.json()
    assert status["pending"] > 0
    assert status["is_complete"] is False


# ---------------------------------------------------------------------------
# Test 6 — Export before processing (must fail with 422)
# ---------------------------------------------------------------------------

def test_export_before_processing_fails(base_url: str, test_project: dict) -> None:
    """POST /api/projects/{id}/export/rvtools without normalized records → 422."""
    project_id = test_project["id"]

    resp = httpx.post(
        f"{base_url}/api/projects/{project_id}/export/rvtools",
        timeout=10,
    )
    # No complete normalized records → expect 422 Unprocessable Entity
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Test 7 — Validate export structure (no HTTP, no Claude)
# ---------------------------------------------------------------------------

def test_generator_and_validator() -> None:
    """Generate an xlsx from synthetic normalized data, then validate its structure."""
    from services.rvtools_generator import generate_rvtools_xlsx
    from services.validator import validate_rvtools_xlsx

    # Minimal synthetic normalized record
    synthetic_record = {
        "vinfo": {
            "vm_name": "TEST-VM-01",
            "powerstate": "poweredOn",
            "template": "False",
            "cpus": 4,
            "memory_mb": 8192,
            "nics": 1,
            "disks": 1,
            "provisioned_mb": 51200,
            "in_use_mb": 40960,
            "datacenter": "DC-Test",
            "cluster": "CL-Test",
            "host": "esxi-host-01",
            "os_config": "Microsoft Windows Server 2022",
            "os_vmware_tools": "Microsoft Windows Server 2022",
        },
        "vnetwork": [
            {
                "vm_name": "TEST-VM-01",
                "powerstate": "poweredOn",
                "template": "False",
                "srm_placeholder": "False",
                "nic_label": "Network adapter 1",
                "adapter": "VMXNET3",
                "network": "VM Network",
                "switch": "vSwitch0",
                "connected": "True",
                "starts_connected": "True",
                "mac_address": "00:50:56:aa:bb:cc",
                "type": "vmxnet3",
                "ipv4_address": "192.168.1.10",
                "ipv6_address": None,
                "direct_path_io": "False",
                "internal_sort_column": None,
                "annotation": None,
            }
        ],
        "vpartition": [
            {
                "vm_name": "TEST-VM-01",
                "powerstate": "poweredOn",
                "template": "False",
                "disk_label": "Hard disk 1",
                "capacity_mb": 51200,
                "consumed_mb": 40960,
                "free_mb": 10240,
                "free_pct": 20.0,
                "datacenter": "DC-Test",
                "cluster": "CL-Test",
                "host": "esxi-host-01",
                "os_config": "Microsoft Windows Server 2022",
                "os_vmware_tools": "Microsoft Windows Server 2022",
            }
        ],
        "vhost": {
            "host_name": "esxi-host-01",
            "datacenter": "DC-Test",
            "cluster": "CL-Test",
            "config_status": "Connected",
            "cpu_model": "Intel(R) Xeon(R) Gold 6154",
            "speed_mhz": 3000,
            "ht_available": "Yes",
            "ht_active": "Yes",
            "num_cpu": 2,
            "cores_per_cpu": 18,
            "num_cores": 36,
            "cpu_usage_pct": 5.0,
            "memory_mb": 393216,
            "memory_usage_pct": 20.0,
            "console": None,
            "num_nics": 4,
            "num_hbas": 2,
            "num_vms": 1,
            "vms_per_core": 0.03,
            "num_vcpus": 4,
            "vcpus_per_core": 0.11,
            "vram_mb": 8192,
            "vm_used_memory": 8192,
            "vm_memory_swapped": 0,
            "vm_memory_ballooned": 0,
            "esx_version": "VMware ESXi 8.0.0",
            "vendor": "Dell",
            "model": "PowerEdge R750",
        },
    }

    xlsx_bytes = generate_rvtools_xlsx([synthetic_record], "pytest-project")
    assert isinstance(xlsx_bytes, bytes)
    assert len(xlsx_bytes) > 0

    result = validate_rvtools_xlsx(xlsx_bytes)

    assert result["valid"] is True, f"Validation errors: {result['errors']}"
    # The generator produces all 22 RVTools sheets; extra sheets are permitted (warnings, not errors)
    assert {"vInfo", "vNetwork", "vPartition", "vHost"}.issubset(set(result["sheets"]))
    assert result["errors"] == []
    # Extra sheets produce a warning — confirm no "no data rows" warnings fired on required sheets
    assert not any("no data rows" in w for w in result["warnings"])


# ---------------------------------------------------------------------------
# Test 8 — Cleanup (delete the test project)
# ---------------------------------------------------------------------------

def test_delete_project(base_url: str, test_project: dict) -> None:
    """DELETE /api/projects/{id} should return 204 No Content."""
    project_id = test_project["id"]

    # We intentionally call delete here as a test; the fixture will attempt it
    # again during teardown but that's safe (404 is caught).
    resp = httpx.delete(f"{base_url}/api/projects/{project_id}", timeout=10)
    assert resp.status_code == 204
