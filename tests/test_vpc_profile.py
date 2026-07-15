"""Unit tests for _select_vpc_profile() in vpc_calculator_generator.

Covers:
  - Flex-Nano (nxf): 5 fixed profiles for ≤2 vCPU / ≤4 GB workloads
  - Flex-Compute (cxf): 2 GB/vCPU, max 64 vCPU
  - Flex-Balanced (bxf): 4 GB/vCPU, max 64 vCPU; bxf-24x96 IS valid; bxf-12/20 are NOT
  - Flex-Memory (mxf): 8 GB/vCPU, max 64 vCPU
  - Fixed profiles: cx2-96x192, mx2-96x768, ux2d, vx2d up to 176 vCPU
  - Assumption fallback: spec exceeds catalog max → vx2d-176x2464 with flag="assumption"
  - Every server ALWAYS gets a profile — no server is ever left without one
  - CPU snapping: non-catalog CPU counts round up to next valid size per family
  - Bug A: RAM rounding (snap_ram = snap_cpu × ratio, not ram_gb directly)
  - Bug B: category boundary (exact ratio determines family, no gray zone)
"""
import sys
import os

# Ensure the api package is on the path when run from the repo root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

import pytest
from services.vpc_calculator_generator import _select_vpc_profile


# ---------------------------------------------------------------------------
# Flex-Nano (nxf) — fixed profiles for tiny workloads ≤2 vCPU / ≤4 GB RAM
# ---------------------------------------------------------------------------

class TestFlexNano:
    def test_1cpu_1gb(self):
        cat, name, flag = _select_vpc_profile(1, 1)
        assert cat == "Flex-Nano"
        assert name == "nxf-1x1"
        assert flag == ""

    def test_1cpu_2gb(self):
        cat, name, flag = _select_vpc_profile(1, 2)
        assert cat == "Flex-Nano"
        assert name == "nxf-1x2"
        assert flag == ""

    def test_1cpu_4gb_max_nano(self):
        cat, name, flag = _select_vpc_profile(1, 4)
        assert cat == "Flex-Nano"
        assert name == "nxf-1x4"
        assert flag == ""

    def test_2cpu_1gb(self):
        cat, name, flag = _select_vpc_profile(2, 1)
        assert cat == "Flex-Nano"
        assert name == "nxf-2x1"
        assert flag == ""

    def test_2cpu_2gb(self):
        cat, name, flag = _select_vpc_profile(2, 2)
        assert cat == "Flex-Nano"
        assert name == "nxf-2x2"
        assert flag == ""

    def test_1cpu_3gb_rounds_up_to_nxf_1x4(self):
        # 1 vCPU / 3 GB — no nxf-1x3 exists, rounds up to nxf-1x4
        cat, name, flag = _select_vpc_profile(1, 3)
        assert cat == "Flex-Nano"
        assert name == "nxf-1x4"
        assert flag == ""

    def test_2cpu_4gb_falls_through_to_cxf(self):
        # 2 vCPU / 4 GB — nxf has no 2-vCPU profile with ≥4 GB (nxf-2x2 is max for 2 vCPU)
        # → falls through to cxf: cxf-2x4
        cat, name, flag = _select_vpc_profile(2, 4)
        assert cat == "Flex-Compute"
        assert name == "cxf-2x4"
        assert flag == ""

    def test_1cpu_5gb_falls_through_to_bxf(self):
        # 1 vCPU / 5 GB — exceeds all nxf RAM caps (nano max for 1 vCPU is 4 GB)
        # STEP 1 nano: skip (5 > 4).
        # STEP 2 cxf: snap_cpu=2, snap_ram=2×2=4 < 5 → skip.
        #        bxf: snap_cpu=2, snap_ram=2×4=8 ≥ 5 → bxf-2x8
        cat, name, flag = _select_vpc_profile(1, 5)
        assert cat == "Flex-Balanced"
        assert name == "bxf-2x8"
        assert flag == ""


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
        cat, name, flag = _select_vpc_profile(8, 16)
        assert cat == "Flex-Compute"
        assert flag == ""

    def test_max_flex_compute(self):
        cat, name, flag = _select_vpc_profile(64, 128)
        assert cat == "Flex-Compute"
        assert name == "cxf-64x128"
        assert flag == ""

    def test_96cpu_192gb_gets_fixed_profile_not_cxf(self):
        # msplhn100a case: 96 vCPUs > Flex max (64) → fixed profile cx2-96x192
        # cxf-96x192 does NOT exist as a Flex profile
        cat, name, flag = _select_vpc_profile(96, 192)
        assert cat == "Compute"
        assert name == "cx2-96x192"
        assert flag == "fixed_profile"


# ---------------------------------------------------------------------------
# Flex-Balanced (bxf) — 4 GB/vCPU
# ---------------------------------------------------------------------------

class TestFlexBalanced:
    def test_baseline_8cpu_32ram(self):
        cat, name, flag = _select_vpc_profile(8, 32)
        assert cat == "Flex-Balanced"
        assert name == "bxf-8x32"
        assert flag == ""

    def test_bxf_24x96_is_valid(self):
        # bxf-24x96 IS a real IBM catalog profile (24 is valid for bxf)
        cat, name, flag = _select_vpc_profile(24, 96)
        assert cat == "Flex-Balanced"
        assert name == "bxf-24x96"
        assert flag == ""

    def test_bxf_24x96_also_covers_lower_ram(self):
        # 24 vCPU / 80 GB — cxf-24x48 can't cover 80 GB → bxf-24x96 covers it
        cat, name, flag = _select_vpc_profile(24, 80)
        assert cat == "Flex-Balanced"
        assert name == "bxf-24x96"
        assert flag == ""

    def test_bug_a_ram_overflow_escalates_family(self):
        # Bug A: 8 vCPU / 36 GB — bxf gives 8×4=32 < 36 → mxf-8x64
        cat, name, flag = _select_vpc_profile(8, 36)
        assert cat == "Flex-Memory"
        assert name == "mxf-8x64"
        assert flag == ""

    def test_bug_b_category_boundary_ratio_2_5(self):
        # Bug B: 8 vCPU / 20 GB — cxf gives only 16 GB → bxf-8x32
        cat, name, flag = _select_vpc_profile(8, 20)
        assert cat == "Flex-Balanced"
        assert name == "bxf-8x32"
        assert flag == ""

    def test_ratio_just_above_2(self):
        cat, name, flag = _select_vpc_profile(8, 17)
        assert cat == "Flex-Balanced"
        assert name == "bxf-8x32"
        assert flag == ""

    def test_8cpu_65gb_falls_to_fixed(self):
        # 8 vCPU / 65 GB — mxf-8x64 gives only 64 GB → falls to fixed profile.
        # First fixed entry where p_vcpu>=8 AND p_ram>=65 is cx2-96x192 (96≥8, 192≥65).
        cat, name, flag = _select_vpc_profile(8, 65)
        assert cat == "Compute"
        assert name == "cx2-96x192"
        assert flag == "fixed_profile"


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
        # 8 vCPU / 44 GB → bxf gives 32 < 44 → mxf-8x64
        cat, name, flag = _select_vpc_profile(8, 44)
        assert cat == "Flex-Memory"
        assert name == "mxf-8x64"
        assert flag == ""

    def test_mxf_ram_at_exact_capacity(self):
        cat, name, flag = _select_vpc_profile(8, 64)
        assert cat == "Flex-Memory"
        assert name == "mxf-8x64"
        assert flag == ""

    def test_mxf_just_over_capacity_falls_to_fixed(self):
        # 8 vCPU / 65 GB → mxf gives 64 < 65 → first fixed covering it: cx2-96x192
        cat, name, flag = _select_vpc_profile(8, 65)
        assert flag == "fixed_profile"
        assert name == "cx2-96x192"

    def test_mxf_large_cpu_overflow_falls_to_fixed(self):
        # 32 vCPU / 350 GB — mxf-32x256 gives only 256 GB → first fixed covering it:
        # mx2-96x768 (96≥32, 768≥350). cx2-96x192 has only 192 GB which is < 350.
        cat, name, flag = _select_vpc_profile(32, 350)
        assert flag == "fixed_profile"
        assert name == "mx2-96x768"

    def test_max_flex_memory(self):
        cat, name, flag = _select_vpc_profile(64, 512)
        assert cat == "Flex-Memory"
        assert name == "mxf-64x512"
        assert flag == ""

    def test_64cpu_513gb_falls_to_fixed(self):
        # 64 vCPU / 513 GB → mxf-64x512 gives only 512 GB → fixed ux2d or vx2d
        _, _, flag = _select_vpc_profile(64, 513)
        assert flag == "fixed_profile"


# ---------------------------------------------------------------------------
# CPU snapping — per-family catalog enforcement
# ---------------------------------------------------------------------------

class TestCPUSnapping:
    def test_cpu_10_bxf_no_12_snaps_to_16(self):
        # bxf has no 12-vCPU → snaps to 16 → bxf-16x64
        cat, name, flag = _select_vpc_profile(10, 40)
        assert cat == "Flex-Balanced"
        assert name == "bxf-16x64"
        assert flag == ""

    def test_cpu_12_bxf_no_12_snaps_to_16(self):
        # phxldb101 case: 12 CPUs → bxf no 12 → snap to 16
        cat, name, flag = _select_vpc_profile(12, 48)
        assert name == "bxf-16x64"    # NOT bxf-12x48
        assert flag == ""

    def test_cpu_20_bxf_no_20_snaps_to_24(self):
        # bxf has no 20-vCPU → snaps to 24 → bxf-24x96
        cat, name, flag = _select_vpc_profile(20, 80)
        assert name == "bxf-24x96"    # NOT bxf-20x80 (bxf now has 24)
        assert flag == ""

    def test_cpu_24_bxf_has_24(self):
        # bxf DOES have 24-vCPU → bxf-24x96 is valid
        cat, name, flag = _select_vpc_profile(24, 96)
        assert cat == "Flex-Balanced"
        assert name == "bxf-24x96"
        assert flag == ""

    def test_cpu_24_cxf_has_24(self):
        # cxf DOES have 24-vCPU → cxf-24x48 is valid
        cat, name, flag = _select_vpc_profile(24, 48)
        assert cat == "Flex-Compute"
        assert name == "cxf-24x48"
        assert flag == ""

    def test_cpu_0_treated_as_1_goes_nano(self):
        # 0 vCPU → treated as 1; 1 vCPU / 1 GB → nxf-1x1
        cat, name, flag = _select_vpc_profile(0, 1)
        assert cat == "Flex-Nano"
        assert name == "nxf-1x1"
        assert flag == ""


# ---------------------------------------------------------------------------
# Fixed-profile cascade — >64 vCPU servers
# ---------------------------------------------------------------------------

class TestFixedProfiles:
    def test_96cpu_192gb_compute(self):
        # Smallest fixed profile covering 96 vCPU / 192 GB = cx2-96x192
        cat, name, flag = _select_vpc_profile(96, 192)
        assert cat == "Compute"
        assert name == "cx2-96x192"
        assert flag == "fixed_profile"

    def test_96cpu_500gb_memory(self):
        # 96 vCPU / 500 GB — cx2-96x192 RAM too small (192 < 500) → mx2-96x768
        cat, name, flag = _select_vpc_profile(96, 500)
        assert cat == "Memory"
        assert name == "mx2-96x768"
        assert flag == "fixed_profile"

    def test_96cpu_769gb_very_high_memory(self):
        # 96 vCPU / 769 GB — mx2-96x768 RAM too small → ux2d-100x2800
        cat, name, flag = _select_vpc_profile(96, 769)
        assert cat == "Very High Memory"
        assert name == "ux2d-100x2800"
        assert flag == "fixed_profile"

    def test_100cpu_400gb_very_high_memory(self):
        cat, name, flag = _select_vpc_profile(100, 400)
        assert cat == "Very High Memory"
        assert name == "ux2d-100x2800"
        assert flag == "fixed_profile"

    def test_112cpu_3072gb_very_high_memory_max(self):
        cat, name, flag = _select_vpc_profile(112, 3072)
        assert cat == "Very High Memory"
        assert name == "ux2d-112x3072"
        assert flag == "fixed_profile"

    def test_88cpu_1232gb_very_high_memory(self):
        # 88 vCPU / 1232 GB — first fixed where p_vcpu≥88 AND p_ram≥1232:
        # ux2d-100x2800 (100≥88, 2800≥1232) comes before vx2d-88x1232 in the catalog
        cat, name, flag = _select_vpc_profile(88, 1232)
        assert cat == "Very High Memory"
        assert name == "ux2d-100x2800"
        assert flag == "fixed_profile"

    def test_144cpu_ultra_high_memory(self):
        cat, name, flag = _select_vpc_profile(144, 1000)
        assert cat == "Ultra High Memory"
        assert name == "vx2d-144x2016"
        assert flag == "fixed_profile"

    def test_176cpu_ultra_high_memory_catalog_max(self):
        cat, name, flag = _select_vpc_profile(176, 2464)
        assert cat == "Ultra High Memory"
        assert name == "vx2d-176x2464"
        assert flag == "fixed_profile"

    def test_65cpu_130gb_flex_exhausted_falls_to_fixed(self):
        # 65 vCPU just exceeds Flex max → first fixed that covers it
        cat, name, flag = _select_vpc_profile(65, 130)
        assert flag == "fixed_profile"
        assert name == "cx2-96x192"


# ---------------------------------------------------------------------------
# Assumption fallback — spec exceeds entire catalog
# ---------------------------------------------------------------------------

class TestAssumptionFallback:
    def test_200cpu_exceeds_all(self):
        # 200 vCPU > 176 (vx2d max) → assumption fallback
        cat, name, flag = _select_vpc_profile(200, 1000)
        assert flag == "assumption"
        assert name == "vx2d-176x2464"
        assert cat == "Ultra High Memory"

    def test_extreme_ram_exceeds_all(self):
        # 8 vCPU / 4000 GB — beyond ux2d-112x3072 RAM cap
        cat, name, flag = _select_vpc_profile(8, 4000)
        assert flag == "assumption"
        assert name == "vx2d-176x2464"

    def test_177cpu_exceeds_catalog_max(self):
        _, _, flag = _select_vpc_profile(177, 3000)
        assert flag == "assumption"


# ---------------------------------------------------------------------------
# Additional real-world cases
# ---------------------------------------------------------------------------

class TestRealWorld:
    def test_typical_windows_server(self):
        cat, name, flag = _select_vpc_profile(4, 16)
        assert cat == "Flex-Balanced"
        assert name == "bxf-4x16"
        assert flag == ""

    def test_typical_small_linux(self):
        # 2 vCPU / 4 GB — nxf has no 2-vCPU profile with ≥4 GB → falls to cxf-2x4
        cat, name, flag = _select_vpc_profile(2, 4)
        assert cat == "Flex-Compute"
        assert name == "cxf-2x4"
        assert flag == ""

    def test_large_db_server(self):
        cat, name, flag = _select_vpc_profile(32, 256)
        assert cat == "Flex-Memory"
        assert name == "mxf-32x256"
        assert flag == ""

    def test_mexm1bapps15_was_bxf_8x36(self):
        # Original reported bug: bxf-8x36 is not real → mxf-8x64
        cat, name, flag = _select_vpc_profile(8, 36)
        assert name != "bxf-8x36"
        assert flag == ""
        assert name == "mxf-8x64"

    def test_msplhn100a_96cpu_192gb(self):
        # msplhn100a: 96 vCPU — must get a real profile, NOT be excepted
        cat, name, flag = _select_vpc_profile(96, 192)
        assert name == "cx2-96x192"
        assert flag == "fixed_profile"   # on main sheet, not Exceptions
