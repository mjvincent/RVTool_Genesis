"""Unit tests for _select_vpc_profile() in vpc_calculator_generator.

Covers:
  - All three Flex families at clean baseline specs
  - Bug A fix: RAM rounding (snap_ram must be a cpu-step multiple, not ratio multiple)
  - Bug B fix: category boundary (no gray zone — exact ratio is the boundary)
  - Boundary conditions at exact ratio values
  - CPU snapping (non-standard CPU counts round up to nearest standard size)
  - Oversized specs (CPU > 128 or ratio > 8) → no_matching_profile
"""
import sys
import os

# Ensure the api package is on the path when run from the repo root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

import pytest
from services.vpc_calculator_generator import _select_vpc_profile


# ---------------------------------------------------------------------------
# Flex-Compute (cxf) — 2 GB/vCPU
# ---------------------------------------------------------------------------

class TestFlexCompute:
    def test_baseline_8cpu_16ram(self):
        cat, name, flag = _select_vpc_profile(8, 16)
        assert cat == "Flex-Compute"
        assert name == "cxf-8x16"
        assert flag == ""

    def test_baseline_4cpu_8ram(self):
        cat, name, flag = _select_vpc_profile(4, 8)
        assert cat == "Flex-Compute"
        assert name == "cxf-4x8"
        assert flag == ""

    def test_ratio_exactly_2(self):
        # ratio = 2.0 exactly → still Flex-Compute
        cat, name, flag = _select_vpc_profile(8, 16)
        assert cat == "Flex-Compute"
        assert flag == ""

    def test_max_flex_compute(self):
        cat, name, flag = _select_vpc_profile(96, 192)
        assert cat == "Flex-Compute"
        assert name == "cxf-96x192"
        assert flag == ""


# ---------------------------------------------------------------------------
# Flex-Balanced (bxf) — 4 GB/vCPU
# ---------------------------------------------------------------------------

class TestFlexBalanced:
    def test_baseline_8cpu_32ram(self):
        cat, name, flag = _select_vpc_profile(8, 32)
        assert cat == "Flex-Balanced"
        assert name == "bxf-8x32"
        assert flag == ""

    def test_bug_a_ram_overflow_escalates_family(self):
        # Bug A root cause: 8 vCPU / 36 GB — ratio = 36/8 = 4.5 > 4.0
        # bxf (4 GB/vCPU) only gives 8×4=32 GB — not enough.
        # Correct: escalate to mxf (8 GB/vCPU) → 8×8=64 GB.
        # Old code produced the INVALID "bxf-8x36" (not a real profile).
        cat, name, flag = _select_vpc_profile(8, 36)
        assert cat == "Flex-Memory"
        assert name == "mxf-8x64"
        assert flag == ""

    def test_bug_b_category_boundary_ratio_2_5(self):
        # Bug B: 8 vCPU / 20 GB (ratio=2.5) — 2.5 > 2.0, so cxf (2 GB/vCPU) gives only 16 GB.
        # Correct: bxf (4 GB/vCPU) → 8×4=32 GB covers it.
        # Old code assigned cxf and produced cxf-8x16 (under-provisioned by 4 GB).
        cat, name, flag = _select_vpc_profile(8, 20)
        assert cat == "Flex-Balanced"
        assert name == "bxf-8x32"
        assert flag == ""

    def test_ratio_just_above_2(self):
        # 8 vCPU / 17 GB (ratio=2.125) → bxf covers it with 8×4=32 GB
        cat, name, flag = _select_vpc_profile(8, 17)
        assert cat == "Flex-Balanced"
        assert name == "bxf-8x32"
        assert flag == ""

    def test_ram_overflow_escalates_to_mxf(self):
        # 8 vCPU / 65 GB — ratio=65/8=8.125 > 8.0
        # mxf at 8 GB/vCPU: 8×8=64 < 65 → ratio > 8 → no_matching_profile
        cat, name, flag = _select_vpc_profile(8, 65)
        assert flag == "no_matching_profile"


# ---------------------------------------------------------------------------
# Flex-Memory (mxf) — 8 GB/vCPU
# ---------------------------------------------------------------------------

class TestFlexMemory:
    def test_baseline_8cpu_64ram(self):
        cat, name, flag = _select_vpc_profile(8, 64)
        assert cat == "Flex-Memory"
        assert name == "mxf-8x64"
        assert flag == ""

    def test_bug_b_category_boundary_ratio_4_5(self):
        # Bug B: 8 vCPU / 44 GB (ratio=5.5) → was bxf-8x44 (invalid!), must be mxf-8x64
        cat, name, flag = _select_vpc_profile(8, 44)
        assert cat == "Flex-Memory"
        assert name == "mxf-8x64"
        assert flag == ""

    def test_mxf_ram_at_exact_capacity(self):
        # 8 vCPU / 64 GB — ratio=8.0 exactly → mxf covers it
        cat, name, flag = _select_vpc_profile(8, 64)
        assert cat == "Flex-Memory"
        assert name == "mxf-8x64"
        assert flag == ""

    def test_mxf_just_over_capacity(self):
        # 8 vCPU / 65 GB — ratio=8.125 > 8 → no_matching_profile
        cat, name, flag = _select_vpc_profile(8, 65)
        assert flag == "no_matching_profile"

    def test_mxf_large_cpu_overflow(self):
        # 32 vCPU / 350 GB — ratio=10.9 > 8 → no_matching_profile
        cat, name, flag = _select_vpc_profile(32, 350)
        assert flag == "no_matching_profile"

    def test_max_flex_memory(self):
        # mxf has no 128-vCPU size — largest is 96. Should flag no_matching_profile.
        cat, name, flag = _select_vpc_profile(128, 1024)
        assert flag == "no_matching_profile"


# ---------------------------------------------------------------------------
# CPU snapping — per-family catalog enforcement
# ---------------------------------------------------------------------------

class TestCPUSnapping:
    def test_cpu_10_bxf_no_12_snaps_to_16(self):
        # 10 CPUs, 40 GB RAM. bxf has no 12-vCPU → snaps to 16 → bxf-16x64
        # bxf-12x48 is NOT a real IBM VPC profile and must never be produced.
        cat, name, flag = _select_vpc_profile(10, 40)
        assert cat == "Flex-Balanced"
        assert name == "bxf-16x64"
        assert flag == ""

    def test_cpu_12_bxf_no_12_snaps_to_16(self):
        # phxldb101 case: 12 CPUs requested → bxf has no 12-vCPU → snap to 16
        cat, name, flag = _select_vpc_profile(12, 48)
        assert name == "bxf-16x64"    # NOT bxf-12x48
        assert flag == ""

    def test_cpu_20_bxf_no_20_snaps_to_32(self):
        # bxf has no 20-vCPU size → snaps to 32 → bxf-32x128
        cat, name, flag = _select_vpc_profile(20, 80)
        assert name == "bxf-32x128"   # NOT bxf-20x80
        assert flag == ""

    def test_cpu_24_bxf_no_24_snaps_to_32(self):
        # bxf has no 24-vCPU size → snaps to 32 → bxf-32x128
        cat, name, flag = _select_vpc_profile(24, 96)
        assert name == "bxf-32x128"   # NOT bxf-24x96
        assert flag == ""

    def test_cpu_24_cxf_has_24(self):
        # cxf DOES have a 24-vCPU size → cxf-24x48 is a real catalog profile
        cat, name, flag = _select_vpc_profile(24, 48)
        assert cat == "Flex-Compute"
        assert name == "cxf-24x48"
        assert flag == ""

    def test_cpu_1_snaps_to_2(self):
        # 1 CPU → snaps to 2 (minimum Flex size across all families)
        cat, name, flag = _select_vpc_profile(1, 4)
        assert cat == "Flex-Compute"
        assert name == "cxf-2x4"
        assert flag == ""

    def test_cpu_0_treated_as_1_snaps_to_2(self):
        cat, name, flag = _select_vpc_profile(0, 4)
        assert cat == "Flex-Compute"
        assert name == "cxf-2x4"
        assert flag == ""


# ---------------------------------------------------------------------------
# no_matching_profile cases
# ---------------------------------------------------------------------------

class TestNoMatchingProfile:
    def test_cpu_exceeds_96_mxf_max(self):
        # mxf largest valid CPU is 96. 128 vCPUs exceeds it → no_matching_profile.
        _, _, flag = _select_vpc_profile(128, 1024)
        assert flag == "no_matching_profile"

    def test_cpu_exceeds_96_bxf_max(self):
        # bxf largest valid CPU is also 96.
        _, _, flag = _select_vpc_profile(100, 400)
        assert flag == "no_matching_profile"

    def test_ratio_exceeds_8(self):
        # 8 vCPU / 1000 GB (ratio=125) → beyond all Flex families
        _, _, flag = _select_vpc_profile(8, 1000)
        assert flag == "no_matching_profile"

    def test_mxf_max_cpu_96_just_fits(self):
        # mxf largest is 96-vCPU × 8 GB = 768 GB → exactly fits
        cat, name, flag = _select_vpc_profile(96, 768)
        assert cat == "Flex-Memory"
        assert name == "mxf-96x768"
        assert flag == ""

    def test_mxf_max_cpu_96_just_over(self):
        # 96 vCPU / 769 GB → 769 > 768 → no Flex family can cover it
        _, _, flag = _select_vpc_profile(96, 769)
        assert flag == "no_matching_profile"


# ---------------------------------------------------------------------------
# Additional real-world cases
# ---------------------------------------------------------------------------

class TestRealWorld:
    def test_typical_windows_server(self):
        # 4 vCPU / 16 GB — ratio=4.0 exactly → bxf covers it
        cat, name, flag = _select_vpc_profile(4, 16)
        assert cat == "Flex-Balanced"
        assert name == "bxf-4x16"
        assert flag == ""

    def test_typical_small_linux(self):
        # 2 vCPU / 4 GB — ratio=2.0 → cxf covers it
        cat, name, flag = _select_vpc_profile(2, 4)
        assert cat == "Flex-Compute"
        assert name == "cxf-2x4"
        assert flag == ""

    def test_large_db_server(self):
        # 32 vCPU / 256 GB — ratio=8.0 → mxf covers it exactly
        cat, name, flag = _select_vpc_profile(32, 256)
        assert cat == "Flex-Memory"
        assert name == "mxf-32x256"
        assert flag == ""

    def test_mexm1bapps15_was_bxf_8x36(self):
        # The original reported bug: MEXM1BAPPS15 normalized to 8 vCPU / 36 GB RAM
        # Old code produced invalid "bxf-8x36". Correct: ratio=4.5 → mxf-8x64.
        cat, name, flag = _select_vpc_profile(8, 36)
        assert name != "bxf-8x36", "bxf-8x36 is not a valid IBM VPC profile"
        assert flag == ""
        assert name == "mxf-8x64"
