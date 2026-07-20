"""Model benchmark service.

Runs a fixed corpus of 8 synthetic server-normalisation cases through two LLM
backends and returns a scored comparison report.  Scoring is 50 % accuracy +
50 % speed so that both response quality and latency matter equally.

Accuracy: fraction of deterministic expected fields that the LLM produces
correctly after the standard sanitisation pass.

Speed score: clamp(1 - avg_latency_ms / LATENCY_CEILING_MS, 0, 1) * 100
where LATENCY_CEILING_MS = 30 000.  A model that exceeds 30 s per record on
average scores 0 on speed regardless of accuracy.

Composite: (accuracy_pct * 0.5) + (speed_score * 0.5)
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

# We import only the pure functions that don't touch the DB or global settings.
from services.ai_normalizer import (
    _build_prompt,         # noqa: PLC2701  (private but stable)
    _extract_json,         # noqa: PLC2701
    _sanitize_numeric_fields,  # noqa: PLC2701
    _is_powervs_os,        # noqa: PLC2701
)

logger = logging.getLogger(__name__)

LATENCY_CEILING_MS: float = 30_000.0  # 30 s — models slower than this score 0 on speed


# ---------------------------------------------------------------------------
# Benchmark corpus
# ---------------------------------------------------------------------------

@dataclass
class BenchmarkCase:
    """One synthetic server record with its expected normalised field values."""
    id: int
    description: str
    raw_row: dict[str, Any]
    # Flat dict of dotted-path → expected value.  Only deterministic fields are
    # included — fields that require creative defaults (datacenter, cluster…)
    # are intentionally omitted so scoring is objective.
    expected_fields: dict[str, Any]


BENCHMARK_CASES: list[BenchmarkCase] = [
    # ------------------------------------------------------------------
    # Case 1 — Windows Server 2022, RAM expressed as bare integer (no unit)
    # Critical: model must infer "64" means 64 GB and emit 65 536 MB.
    # ------------------------------------------------------------------
    BenchmarkCase(
        id=1,
        description="Windows Server 2022 — RAM as bare integer '64' (should be 65 536 MB)",
        raw_row={
            "server_name": "WIN-APP-01",
            "os":           "Windows Server 2022",
            "vcpus":        8,
            "ram":          64,          # intentionally no unit — should be treated as GB
            "disk_gb":      200,
        },
        expected_fields={
            "server_type":    "vm",
            "vinfo.cpus":     8,
            "vinfo.memory_mb": 65_536,
        },
    ),

    # ------------------------------------------------------------------
    # Case 2 — AIX server
    # Critical: server_type must be "powervs", os_config must contain "AIX".
    # ------------------------------------------------------------------
    BenchmarkCase(
        id=2,
        description="AIX 7.2 server — must be classified as powervs",
        raw_row={
            "server_name": "AIX-PROD-01",
            "os":          "AIX 7.2",
            "vcpus":       4,
            "ram_gb":      32,
            "disk_gb":     100,
        },
        expected_fields={
            "server_type":  "powervs",
        },
    ),

    # ------------------------------------------------------------------
    # Case 3 — IBM i server
    # Critical: server_type must be "powervs", os_config must contain "IBM i".
    # ------------------------------------------------------------------
    BenchmarkCase(
        id=3,
        description="IBM i 7.4 — must be classified as powervs",
        raw_row={
            "server_name": "IBMI-ERP-01",
            "os":          "IBM i 7.4",
            "vcpus":       2,
            "ram_gb":      16,
            "disk_gb":     500,
        },
        expected_fields={
            "server_type":  "powervs",
        },
    ),

    # ------------------------------------------------------------------
    # Case 4 — RHEL 9 VM, disk expressed as bare integer (likely GB)
    # Critical: server_type must be "vm"; os_config must contain RHEL 9.
    # ------------------------------------------------------------------
    BenchmarkCase(
        id=4,
        description="RHEL 9 VM — disk as bare integer '500' (GB), server_type vm",
        raw_row={
            "server_name": "LNX-WEB-04",
            "os":          "Red Hat Enterprise Linux 9",
            "vcpus":       4,
            "ram_gb":      16,
            "disk":        500,          # no unit — typically GB
        },
        expected_fields={
            "server_type":  "vm",
        },
    ),

    # ------------------------------------------------------------------
    # Case 5 — Windows Server 2019, RAM expressed as "128 GB" (explicit string)
    # Critical: memory_mb must be 131 072.
    # ------------------------------------------------------------------
    BenchmarkCase(
        id=5,
        description="Windows Server 2019 — RAM as '128 GB' string (should be 131 072 MB)",
        raw_row={
            "server_name": "WIN-DB-05",
            "os":          "Windows Server 2019",
            "vcpus":       16,
            "memory":      "128 GB",
            "disk_gb":     300,
        },
        expected_fields={
            "server_type":     "vm",
            "vinfo.cpus":      16,
            "vinfo.memory_mb": 131_072,
        },
    ),

    # ------------------------------------------------------------------
    # Case 6 — Minimal record: name and OS only, all else missing
    # Critical: valid JSON must be produced; vm_name must be non-empty;
    # reasonable defaults must be applied.
    # ------------------------------------------------------------------
    BenchmarkCase(
        id=6,
        description="Minimal record — name and OS only, all other fields absent",
        raw_row={
            "server_name": "BARE-MIN-06",
            "os":          "Ubuntu 20.04 LTS",
        },
        expected_fields={
            "server_type":  "vm",
        },
    ),

    # ------------------------------------------------------------------
    # Case 7 — SAP on Red Hat Linux (Linux-on-Power)
    # Critical: server_type must be "powervs"; os_config must reference SAP.
    # ------------------------------------------------------------------
    BenchmarkCase(
        id=7,
        description="SAP Red Hat Linux — must be classified as powervs",
        raw_row={
            "server_name": "SAP-APP-07",
            "os":          "SAP Red Hat Enterprise Linux",
            "vcpus":       8,
            "ram_gb":      64,
            "disk_gb":     500,
        },
        expected_fields={
            "server_type":  "powervs",
        },
    ),

    # ------------------------------------------------------------------
    # Case 8 — Ubuntu 22.04, explicit vCPU and GB RAM
    # Critical: cpus == 16, memory_mb == 32 768, server_type == "vm".
    # ------------------------------------------------------------------
    BenchmarkCase(
        id=8,
        description="Ubuntu 22.04 — 16 vCPU / 32 GB, standard vm",
        raw_row={
            "server_name": "LNX-K8S-08",
            "os":          "Ubuntu 22.04 LTS",
            "vcpus":       16,
            "ram_gb":      32,
            "disk_gb":     150,
        },
        expected_fields={
            "server_type":    "vm",
            "vinfo.cpus":     16,
            "vinfo.memory_mb": 32_768,
        },
    ),
]


# ---------------------------------------------------------------------------
# LLM call helpers (backend-agnostic)
# ---------------------------------------------------------------------------

_OLLAMA_TIMEOUT = 45.0   # per-case; shorter than the full pipeline timeout
_DMR_TIMEOUT    = 45.0


def _call_ollama_benchmark(prompt: str, base_url: str, model: str) -> str:
    """Call an Ollama /api/generate endpoint and return the raw response text."""
    url = f"{base_url.rstrip('/')}/api/generate"
    payload = {
        "model":  model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.1},
    }
    with httpx.Client(timeout=_OLLAMA_TIMEOUT) as client:
        resp = client.post(url, json=payload)
        resp.raise_for_status()
    raw: str = resp.json().get("response", "")
    if not raw:
        raise ValueError("Ollama returned an empty response")
    return raw


def _call_dmr_benchmark(prompt: str, base_url: str, model: str) -> str:
    """Call a Docker Model Runner (OpenAI-compatible) /v1/chat/completions endpoint."""
    url = f"{base_url.rstrip('/')}/v1/chat/completions"
    payload = {
        "model":       model,
        "messages":    [{"role": "user", "content": prompt}],
        "temperature": 0.1,
    }
    with httpx.Client(timeout=_DMR_TIMEOUT) as client:
        resp = client.post(url, json=payload)
        resp.raise_for_status()
    choices = resp.json().get("choices", [])
    if not choices:
        raise ValueError("Docker Model Runner returned no choices")
    return choices[0]["message"]["content"]


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

# Field aliases: some small models emit alternative key names for the same concept,
# or flatten the vinfo structure entirely.  The scorer tries the canonical path first,
# then each alias in order.
_FIELD_ALIASES: dict[str, list[str]] = {
    "vinfo.cpus":      ["vinfo.num_cpus", "cpus", "num_cpus", "vcpus"],
    "vinfo.memory_mb": ["vinfo.memory", "vinfo.ram_mb", "memory_mb", "ram_mb", "memory", "ram"],
}


def _get_dotted(obj: dict, path: str) -> Any:
    """Retrieve a value from a nested dict using a dotted path (e.g. 'vinfo.memory_mb').

    Falls back gracefully when a nested key is absent.
    """
    parts = path.split(".")
    cur: Any = obj
    for part in parts:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _resolve_field(normalized: dict, path: str) -> Any:
    """Look up a field, trying the canonical path then all registered aliases.

    Handles two real-world failure modes:
    - Flattened output: model emits top-level 'cpus' instead of 'vinfo.cpus'
    - Key aliasing: model emits 'num_cpus' instead of 'cpus'
    """
    val = _get_dotted(normalized, path)
    if val is not None:
        return val
    for alias in _FIELD_ALIASES.get(path, []):
        val = _get_dotted(normalized, alias)
        if val is not None:
            return val
    return None


def score_response(normalized: dict, expected_fields: dict[str, Any]) -> dict[str, Any]:
    """Score a normalised record against the expected fields for one benchmark case.

    Returns a dict with per-field pass/fail and an overall accuracy fraction.
    """
    results: dict[str, bool] = {}
    for path, expected in expected_fields.items():
        actual = _resolve_field(normalized, path)

        if isinstance(expected, int) and path in ("vinfo.cpus", "vinfo.memory_mb"):
            # Numeric fields: accept both the exact MB value and the equivalent GB value.
            # A model that emits memory_mb=32 when the answer is 32768 MB (32 GB) understood
            # the question — it just omitted the ×1024 multiplication.
            try:
                actual_int = int(float(actual)) if actual is not None else None
            except (TypeError, ValueError):
                actual_int = None
            match = actual_int == expected or (
                actual_int is not None
                and path == "vinfo.memory_mb"
                and actual_int * 1024 == expected
            )
        elif isinstance(expected, str):
            # Case-insensitive substring match for os_config-style string fields
            match = (
                isinstance(actual, str)
                and expected.lower() in actual.lower()
            )
        else:
            match = actual == expected

        results[path] = match

    total = len(results)
    passed = sum(1 for v in results.values() if v)
    accuracy = (passed / total) if total > 0 else 0.0

    return {
        "field_results": results,
        "passed": passed,
        "total": total,
        "accuracy": accuracy,
    }


# ---------------------------------------------------------------------------
# Per-model benchmark runner
# ---------------------------------------------------------------------------

@dataclass
class CaseResult:
    case_id: int
    description: str
    valid_json: bool
    field_results: dict[str, bool] = field(default_factory=dict)
    passed: int = 0
    total: int = 0
    latency_ms: float = 0.0
    error: str | None = None


@dataclass
class ModelBenchmarkResult:
    name: str
    backend: str           # "ollama" or "docker_model_runner"
    reachable: bool
    cases: list[CaseResult] = field(default_factory=list)
    accuracy_pct: float = 0.0
    speed_score: float = 0.0
    composite_score: float = 0.0
    avg_latency_ms: float = 0.0


def run_benchmark(
    model_name: str,
    backend: str,          # "ollama" or "docker_model_runner"
    ollama_base_url: str,
    dmr_base_url: str,
) -> ModelBenchmarkResult:
    """Run all BENCHMARK_CASES through one model and return scored results.

    Cases run sequentially to avoid GPU/RAM contention.
    """
    result = ModelBenchmarkResult(name=model_name, backend=backend, reachable=False)

    # Quick reachability check before running all cases
    try:
        if backend == "ollama":
            _probe_url = f"{ollama_base_url.rstrip('/')}/api/tags"
        else:
            _probe_url = f"{dmr_base_url.rstrip('/')}/v1/models"
        with httpx.Client(timeout=5.0) as client:
            client.get(_probe_url).raise_for_status()
        result.reachable = True
    except Exception as exc:  # noqa: BLE001
        logger.warning("Model backend unreachable for %s (%s): %s", model_name, backend, exc)
        return result  # composite stays 0

    total_latency_ms = 0.0
    total_passed = 0
    total_fields = 0

    for case in BENCHMARK_CASES:
        prompt = _build_prompt(case.raw_row)
        t0 = time.perf_counter()
        raw_text: str | None = None
        error_msg: str | None = None

        try:
            if backend == "ollama":
                raw_text = _call_ollama_benchmark(prompt, ollama_base_url, model_name)
            else:
                raw_text = _call_dmr_benchmark(prompt, dmr_base_url, model_name)
        except Exception as exc:  # noqa: BLE001
            error_msg = str(exc)

        latency_ms = (time.perf_counter() - t0) * 1000.0

        # Parse and sanitise the response
        normalized: dict = {}
        valid_json = False
        if raw_text:
            try:
                cleaned = _extract_json(raw_text)
                parsed = json.loads(cleaned)
                normalized = _sanitize_numeric_fields(parsed)
                valid_json = True
            except Exception as exc:  # noqa: BLE001
                error_msg = error_msg or f"JSON parse error: {exc}"

        # Score against expected fields
        if valid_json:
            score = score_response(normalized, case.expected_fields)
            field_results = score["field_results"]
            passed = score["passed"]
            total = score["total"]
        else:
            field_results = {k: False for k in case.expected_fields}
            passed = 0
            total = len(case.expected_fields)

        total_latency_ms += latency_ms
        total_passed += passed
        total_fields += total

        result.cases.append(CaseResult(
            case_id=case.id,
            description=case.description,
            valid_json=valid_json,
            field_results=field_results,
            passed=passed,
            total=total,
            latency_ms=round(latency_ms, 1),
            error=error_msg,
        ))

    n = len(BENCHMARK_CASES)
    result.avg_latency_ms = round(total_latency_ms / n, 1) if n else 0.0
    result.accuracy_pct = round((total_passed / total_fields * 100) if total_fields else 0.0, 1)

    # Speed score: 0–100, ceiling at LATENCY_CEILING_MS
    speed_raw = 1.0 - (result.avg_latency_ms / LATENCY_CEILING_MS)
    result.speed_score = round(max(0.0, min(1.0, speed_raw)) * 100.0, 1)

    # Composite: equal 50/50 weight
    result.composite_score = round(
        (result.accuracy_pct * 0.5) + (result.speed_score * 0.5), 1
    )

    return result


# ---------------------------------------------------------------------------
# Recommendation sentence generator
# ---------------------------------------------------------------------------

def make_recommendation(a: ModelBenchmarkResult, b: ModelBenchmarkResult) -> tuple[str, str]:
    """Return (winner_key, recommendation_sentence) where winner_key is
    'model_a', 'model_b', or 'tie'.
    """
    if not a.reachable and not b.reachable:
        return "tie", "Neither model was reachable — check that both backends are running."
    if not a.reachable:
        return "model_b", f"{b.name} wins by default — {a.name} ({a.backend}) was unreachable."
    if not b.reachable:
        return "model_a", f"{a.name} wins by default — {b.name} ({b.backend}) was unreachable."

    diff = round(a.composite_score - b.composite_score, 1)

    if abs(diff) < 1.0:
        # Too close to call — break tie on accuracy, then speed
        if abs(a.accuracy_pct - b.accuracy_pct) < 1.0:
            return "tie", (
                f"{a.name} and {b.name} are virtually identical "
                f"(composite {a.composite_score} vs {b.composite_score}). "
                "Keep your current model."
            )
        winner, loser = (a, b) if a.accuracy_pct > b.accuracy_pct else (b, a)
        key = "model_a" if winner is a else "model_b"
        return key, (
            f"{winner.name} edges out {loser.name} on accuracy "
            f"({winner.accuracy_pct:.0f}% vs {loser.accuracy_pct:.0f}%) with similar speed."
        )

    winner, loser = (a, b) if diff > 0 else (b, a)
    key = "model_a" if winner is a else "model_b"

    acc_diff = round(winner.accuracy_pct - loser.accuracy_pct, 1)
    lat_diff = round(loser.avg_latency_ms - winner.avg_latency_ms, 0)

    parts: list[str] = []
    if acc_diff >= 1.0:
        parts.append(f"{acc_diff:.0f}% more accurate")
    if lat_diff > 200:
        parts.append(f"{lat_diff / 1000:.1f}s faster per record")
    elif lat_diff < -200:
        parts.append(f"{abs(lat_diff) / 1000:.1f}s slower per record")

    detail = " and ".join(parts) if parts else f"composite score {winner.composite_score} vs {loser.composite_score}"
    return key, (
        f"{winner.name} wins — {detail}. "
        f"Composite: {winner.composite_score} vs {loser.composite_score}."
    )
