"""Curated LLM model catalog and recommendation service.

Maintains a static, hand-curated list of known upgrade paths per provider.
A recommendation is ONLY issued when the catalog has an explicit entry for the
user's current model — no heuristics, no guessing, no false positives.

To update the catalog:
  1. Add new models to CATALOG[provider] (insert at the top — newest first).
  2. Add an entry to SUCCESSOR_MAP[provider][old_model] = new_model if there is
     a clear, confident upgrade path (same tier or better, same provider).
  3. Write a human-readable reason string — this is shown in the Settings UI.
"""
from __future__ import annotations

import logging
import time as _time
from typing import Any

import httpx as _httpx
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModelEntry:
    """A single model entry in the catalog."""
    model_id: str          # Exact model identifier used in API calls
    label: str             # Human-readable display name
    notes: str             # Brief description of strengths


@dataclass(frozen=True)
class ModelRecommendation:
    """A recommendation to upgrade from one model to another."""
    provider: str
    current_model: str
    recommended_model: str
    recommended_label: str
    reason: str            # Shown verbatim in the Settings UI banner


# ---------------------------------------------------------------------------
# Model catalog — ordered newest/best first within each provider
# ---------------------------------------------------------------------------

CATALOG: dict[str, list[ModelEntry]] = {
    "ollama": [
        # Ollama models are user-managed — no automatic recommendations.
        # Listed here for reference only.
        ModelEntry("phi4-mini",         "Phi-4 Mini",              "Default; fast structured extraction on CPU"),
        ModelEntry("llama3.2",          "Llama 3.2 3B",            "Good general purpose, small footprint"),
        ModelEntry("mistral",           "Mistral 7B",              "Strong instruction following"),
        ModelEntry("qwen2.5:7b",        "Qwen 2.5 7B",             "Competitive JSON extraction quality"),
    ],
    "watsonx": [
        ModelEntry("ibm/granite-3-3b-instruct",        "Granite 3.3 3B Instruct",   "Latest Granite 3 series — fast, efficient"),
        ModelEntry("ibm/granite-3-8b-instruct",        "Granite 3 8B Instruct",     "Recommended for structured JSON extraction"),
        ModelEntry("ibm/granite-3-2b-instruct",        "Granite 3 2B Instruct",     "Lightweight; lower accuracy on complex tasks"),
        ModelEntry("meta-llama/llama-3-3-70b-instruct","Llama 3.3 70B Instruct",    "High quality; higher cost and latency"),
        ModelEntry("meta-llama/llama-3-1-8b-instruct", "Llama 3.1 8B Instruct",     "Balanced cost/quality"),
    ],
    "openai": [
        ModelEntry("gpt-4o",       "GPT-4o",        "Highest quality; higher cost"),
        ModelEntry("gpt-4o-mini",  "GPT-4o Mini",   "Recommended — best cost/quality for extraction tasks"),
        ModelEntry("gpt-4-turbo",  "GPT-4 Turbo",   "Legacy; superseded by gpt-4o"),
    ],
    "anthropic": [
        ModelEntry("claude-3-5-sonnet-20241022",  "Claude 3.5 Sonnet",       "Highest quality Anthropic model"),
        ModelEntry("claude-3-5-haiku-20241022",   "Claude 3.5 Haiku",        "Newer Haiku — faster and more capable than 3.0 Haiku"),
        ModelEntry("claude-3-haiku-20240307",     "Claude 3 Haiku",          "Original Haiku; superseded by 3.5 Haiku"),
        ModelEntry("claude-3-opus-20240229",      "Claude 3 Opus",           "Legacy high-quality; expensive"),
    ],
}

# ---------------------------------------------------------------------------
# Successor map — ONLY explicit, confident upgrade paths
#
# Structure: {provider: {current_model_id: recommended_model_id}}
#
# Rules for adding an entry:
#   - The recommended model must be in the same or lower cost tier
#   - The recommended model must be demonstrably better for structured JSON
#     extraction tasks (our primary use case)
#   - When in doubt, do NOT add an entry — no recommendation is better than
#     a wrong one
# ---------------------------------------------------------------------------

SUCCESSOR_MAP: dict[str, dict[str, str]] = {
    "ollama": {
        # No automatic recommendations for local models
    },
    "watsonx": {
        # granite-3-2b → granite-3-8b: same family, more parameters, better extraction accuracy
        "ibm/granite-3-2b-instruct": "ibm/granite-3-8b-instruct",
        # granite-3-8b → granite-3-3b: newer architecture (3.3 series), comparable quality,
        # smaller footprint — upgrade path when IBM releases granite-3-3b to production
        # NOTE: only enable this when granite-3-3b-instruct is GA on watsonx.ai
        # "ibm/granite-3-8b-instruct": "ibm/granite-3-3b-instruct",
    },
    "openai": {
        # gpt-4-turbo → gpt-4o-mini: newer, cheaper, better for JSON extraction tasks
        "gpt-4-turbo": "gpt-4o-mini",
    },
    "anthropic": {
        # claude-3-haiku-20240307 → claude-3-5-haiku-20241022:
        # Same cost tier, newer model, faster and more capable
        "claude-3-haiku-20240307": "claude-3-5-haiku-20241022",
    },
}

# Human-readable reasons for each upgrade path
_REASONS: dict[str, dict[str, str]] = {
    "watsonx": {
        "ibm/granite-3-2b-instruct":
            "Granite 3 8B Instruct produces more accurate structured JSON extractions "
            "than the 2B model and is IBM's recommended model for this use case.",
    },
    "openai": {
        "gpt-4-turbo":
            "GPT-4o Mini is a newer, faster, and more cost-effective model that "
            "outperforms GPT-4 Turbo on structured extraction tasks.",
    },
    "anthropic": {
        "claude-3-haiku-20240307":
            "Claude 3.5 Haiku is the updated Haiku model — faster and more capable "
            "than the original Claude 3 Haiku at the same cost tier.",
    },
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_recommendation(provider: str, current_model: str | None) -> ModelRecommendation | None:
    """Return a recommendation to upgrade the current model, or None.

    Only returns a recommendation when:
      - The provider is not "ollama" (local models are user-managed)
      - The current_model has an explicit entry in SUCCESSOR_MAP
      - The successor model exists in CATALOG

    Args:
        provider:      Active LLM provider ("ollama", "watsonx", "openai", "anthropic").
        current_model: Active model identifier (may be None if not yet configured).

    Returns:
        A ModelRecommendation if a confident upgrade path exists, else None.
    """
    if provider == "ollama" or not current_model:
        return None

    successor_id = SUCCESSOR_MAP.get(provider, {}).get(current_model)
    if not successor_id:
        return None

    # Verify the successor is actually in the catalog
    catalog_entry = next(
        (e for e in CATALOG.get(provider, []) if e.model_id == successor_id),
        None,
    )
    if catalog_entry is None:
        return None

    reason = _REASONS.get(provider, {}).get(current_model, f"A newer model is available: {successor_id}")

    return ModelRecommendation(
        provider=provider,
        current_model=current_model,
        recommended_model=successor_id,
        recommended_label=catalog_entry.label,
        reason=reason,
    )


def get_catalog_models(provider: str) -> list[ModelEntry]:
    """Return the ordered model list for a provider (newest first)."""
    return CATALOG.get(provider, [])


# ---------------------------------------------------------------------------
# Local Ollama model ranking (Sub-Task A — Local LLM Advisor)
# ---------------------------------------------------------------------------

# Task-fit score: how well each Ollama model handles structured JSON extraction.
# Higher = better. Models not in this table default to 5 (neutral/unknown).
#
# Scoring rationale:
#   9–10  Instruction-tuned generalist models proven accurate and fast on this task
#    7–8  Capable generalists; adequate but not optimal
#    5–6  Neutral/unknown — benign generalists without a known track record here
#    3–4  Specialised models (code, vision, math) that are NOT tuned for JSON extraction
#    1–2  Embedding / feature-extraction models — cannot generate text at all
#
# IMPORTANT: Code-specialised models (qwen2.5-coder, codellama, deepseek-coder, etc.)
# must be listed explicitly with low scores.  The prefix-match fallback in
# rank_local_models() would otherwise promote them to their parent family's high score.
_OLLAMA_TASK_FIT: dict[str, int] = {
    # --- Tier 1: excellent structured-extraction models ---
    "phi4":              10,
    "phi4-mini":          9,
    "qwen2.5:14b":       10,
    "qwen2.5:32b":       10,
    "qwen2.5:7b":         9,
    "qwen2.5":            9,   # generic tag fallback for untagged qwen2.5
    "qwen3":              9,   # Qwen 3 series (qwen3:8b, qwen3:14b, qwen3:30b, etc.)
    "qwen3.6":            9,   # 36B MoE variant
    # --- Tier 2: capable generalists ---
    "llama3.3":           8,
    "llama3.2":           7,
    "llama3.1":           7,
    "llama3":             7,   # covers llama3-*-GGUF compound names
    "llama4":             8,   # Llama 4 when available
    "mistral-nemo":       8,
    "mistral":            7,
    "mistral-small":      8,
    "gemma3":             7,
    "gemma4":             8,   # Gemma 4 series
    "gemma2":             6,
    "deepseek-v3":        8,   # DeepSeek V3 — strong JSON extraction
    "deepseek-v4":        9,   # DeepSeek V4
    "deepseek-r2":        8,
    "deepseek-r1":        7,
    "deepseek":           7,   # generic deepseek fallback
    "command-r":          8,   # Cohere Command-R
    "command-r-plus":     9,
    # --- Code-specialised models — NOT suited for JSON extraction ---
    "qwen2.5-coder":      3,
    "qwen2.5-coder:1.5b": 3,
    "qwen2.5-coder:7b":   3,
    "qwen2.5-coder:14b":  3,
    "qwen2.5-coder:32b":  3,
    "qwen3-coder":        3,
    "codellama":          3,
    "deepseek-coder":     3,
    "deepseek-coder-v2":  3,
    "starcoder":          3,
    "starcoder2":         3,
    "codegemma":          3,
    "codeqwen":           3,
    # --- Embedding / feature-extraction models — cannot generate text ---
    "nomic-embed-text":   1,
    "nomic-embed":        1,
    "mxbai-embed-large":  1,
    "mxbai-embed":        1,
    "all-minilm":         1,
    "snowflake-arctic-embed": 1,
    "bge-m3":             1,
    "bge-large":          1,
}

# Ordered prefix table for HuggingFace compound names that won't match the exact
# lookup above (e.g. "qwen3.6-27b-mtp-gguf" → family "qwen3" → score 9).
# Evaluated in order; first match wins.  More specific prefixes listed first.
_FAMILY_PREFIX_SCORES: list[tuple[str, int]] = [
    ("phi4-mini",         9),
    ("phi4",             10),
    ("qwen2.5-coder",     3),
    ("qwen3-coder",       3),
    ("qwen3.6",           9),
    ("qwen3",             9),
    ("qwen2.5",           9),
    ("qwen2",             7),
    ("deepseek-coder",    3),
    ("deepseek-v4",       9),
    ("deepseek-v3",       8),
    ("deepseek-r2",       8),
    ("deepseek-r1",       7),
    ("deepseek",          7),
    ("llama4",            8),
    ("llama3.3",          8),
    ("llama3.2",          7),
    ("llama3.1",          7),
    ("llama3",            7),
    ("gemma4",            8),
    ("gemma-4",           8),   # HuggingFace uses hyphen: gemma-4-27b-it-gguf
    ("gemma3",            7),
    ("gemma-3",           7),
    ("gemma2",            6),
    ("gemma",             6),
    ("mistral-small",     8),
    ("mistral-nemo",      8),
    ("mistral",           7),
    ("command-r-plus",    9),
    ("command-r",         8),
]

# Name fragments that always cap task_fit to 4, regardless of the lookup table.
# Guards against future unknown specialised models inheriting a high family score
# via the prefix-match fallback in rank_local_models().
_SPECIALISED_SUFFIXES: tuple[str, ...] = (
    "-coder", "-code", "-embed", "-embedding", "embedding",
    "-vision", "-vl", "-ocr", "-math",
    "starcoder",
)

# Approximate RAM required (GB) per model family+size.
# Used to flag models that won't fit in available RAM.
_OLLAMA_RAM_GB: dict[str, float] = {
    "phi4-mini":        4.0,
    "phi4":             8.0,
    "llama3.2":         3.0,
    "llama3.1":         5.0,
    "llama3.3":        12.0,
    "qwen2.5:3b":       3.0,
    "qwen2.5:7b":       5.0,
    "qwen2.5:14b":     10.0,
    "qwen2.5:32b":     22.0,
    "mistral":          5.0,
    "mistral-nemo":     8.0,
    "gemma2":           6.0,
    "gemma3":           6.0,
}

# Models we suggest pulling if none installed are a good fit
_PULL_SUGGESTIONS = [
    {"model": "phi4-mini",   "label": "Phi-4 Mini (4 GB RAM)",    "min_ram_gb": 4},
    {"model": "phi4",        "label": "Phi-4 (8 GB RAM)",         "min_ram_gb": 8},
    {"model": "qwen2.5:7b",  "label": "Qwen 2.5 7B (5 GB RAM)",  "min_ram_gb": 5},
    {"model": "qwen2.5:14b", "label": "Qwen 2.5 14B (10 GB RAM)", "min_ram_gb": 10},
]


@dataclass
class RankedModel:
    """An installed Ollama model with advisor scoring."""
    name: str
    size_gb: float
    fits_in_ram: bool
    task_fit: int        # 1–10; higher = better for structured extraction
    recommended: bool    # True for the top-ranked model that fits in RAM
    pull_suggestion: str | None = None  # Non-None means: suggest pulling this instead


def _base_name(model_name: str) -> str:
    """Strip the tag from an Ollama model name for lookup (e.g. 'phi4-mini:latest' → 'phi4-mini')."""
    return model_name.split(":")[0].lower()


def rank_local_models(
    installed: list[dict[str, Any]],
    ram_gb: float,
) -> list[RankedModel]:
    """Rank installed Ollama models for structured JSON extraction on this machine.

    Args:
        installed:  List of Ollama model dicts from /api/tags.
                    Expected keys: name, size (bytes), details.parameter_size.
        ram_gb:     Total machine RAM in GB (from /proc/meminfo or platform).

    Returns:
        List of RankedModel sorted best-first (highest task_fit among those
        that fit in RAM first, then the rest).
    """
    if not installed:
        return []

    ranked: list[RankedModel] = []
    for m in installed:
        name = m.get("name", "")
        size_bytes = m.get("size", 0) or 0
        size_gb = size_bytes / (1024 ** 3)

        base = _base_name(name)

        # Step 1: exact lookup; unknown models default to 5 (neutral), not 1.
        task_fit = _OLLAMA_TASK_FIT.get(base, 5)

        # Step 2: prefix-match fallback for tagged variants not in the table
        # (e.g. "qwen2.5:3b" → inherits "qwen2.5" score of 9).
        # Only fires when the exact lookup returned the neutral default (5).
        if task_fit == 5:
            family = base.split(":")[0]  # strip tag, e.g. "qwen2.5:3b" → "qwen2.5"
            for key, score in _OLLAMA_TASK_FIT.items():
                key_family = key.split(":")[0]
                # Match on stripped family name only — never partial substring match.
                # "qwen2.5-coder" must NOT match "qwen2.5".
                if family == key_family:
                    task_fit = score
                    break

        # Step 3: cap specialised models regardless of what the table says.
        # Catches any future *-coder, *-embed, *-vision variants not yet in the table.
        base_lower = base.lower()
        if any(base_lower.endswith(sfx) or sfx in base_lower for sfx in _SPECIALISED_SUFFIXES):
            task_fit = min(task_fit, 4)

        # RAM fit: use known map first, fall back to actual model file size × 1.2 headroom
        known_ram = _OLLAMA_RAM_GB.get(base) or _OLLAMA_RAM_GB.get(name)
        required_ram = known_ram if known_ram else size_gb * 1.2
        fits = ram_gb >= required_ram

        ranked.append(RankedModel(
            name=name,
            size_gb=round(size_gb, 1),
            fits_in_ram=fits,
            task_fit=task_fit,
            recommended=False,
        ))

    # Sort: fits-in-RAM first, then by task_fit descending, then by size ascending (prefer smaller)
    ranked.sort(key=lambda r: (0 if r.fits_in_ram else 1, -r.task_fit, r.size_gb))

    # Mark the top-ranked model that fits in RAM as recommended
    for r in ranked:
        if r.fits_in_ram:
            r.recommended = True
            break

    return ranked


def get_pull_suggestion(installed_names: list[str], ram_gb: float) -> dict[str, Any] | None:
    """Return the best model to suggest pulling if installed models are all low quality.

    Returns None if a good model (task_fit >= 8) is already installed.
    """
    installed_bases = {_base_name(n) for n in installed_names}
    # Check if any installed model already has high task fit.
    # Use the same two-step lookup as rank_local_models() so the decision is consistent.
    for base in installed_bases:
        fit = _OLLAMA_TASK_FIT.get(base, 5)
        if fit == 5:
            family = base.split(":")[0]
            for key, score in _OLLAMA_TASK_FIT.items():
                if family == key.split(":")[0]:
                    fit = score
                    break
        base_lower = base.lower()
        if any(base_lower.endswith(sfx) or sfx in base_lower for sfx in _SPECIALISED_SUFFIXES):
            fit = min(fit, 4)
        if fit >= 8:
            return None  # already have a good one

    # Suggest the best model that fits in available RAM
    for suggestion in _PULL_SUGGESTIONS:
        if ram_gb >= suggestion["min_ram_gb"]:
            return suggestion

    return None


# ---------------------------------------------------------------------------
# HuggingFace Hub GGUF resolver
# ---------------------------------------------------------------------------

_gguf_cache: dict[str, dict] = {}    # { model_name: { ...result, "_ts": float } }
_GGUF_CACHE_TTL = 3_600              # 1 hour

# Preferred quantization levels in priority order
_PREFERRED_QUANTS = ("Q4_K_M", "Q5_K_M", "Q4_0", "Q8_0")


def resolve_gguf(model_name: str, hf_token: str | None = None) -> dict:
    """Query HuggingFace Hub to find the best GGUF quantization for a model.

    Returns a dict with keys:
      found (bool), hf_repo (str), gguf_file (str),
      pull_command (str), size_gb (float | None)

    Results are cached for 1 hour.
    """
    cache_key = model_name.lower().strip()
    now = _time.time()

    # Return cached result if fresh
    if cache_key in _gguf_cache:
        cached = _gguf_cache[cache_key]
        if now - cached.get("_ts", 0) < _GGUF_CACHE_TTL:
            return {k: v for k, v in cached.items() if k != "_ts"}

    headers: dict[str, str] = {"Accept": "application/json"}
    if hf_token:
        headers["Authorization"] = f"Bearer {hf_token}"

    result: dict = {"found": False, "hf_repo": None, "gguf_file": None, "pull_command": None, "size_gb": None}

    try:
        resp = _httpx.get(
            "https://huggingface.co/api/models",
            params={"search": model_name, "filter": "gguf", "limit": 10},
            headers=headers,
            timeout=10.0,
        )
        resp.raise_for_status()
        models = resp.json()

        if not models:
            _gguf_cache[cache_key] = {**result, "_ts": now}
            return result

        # Pick the best repo: prefer repos whose id contains the model name
        best_repo: dict | None = None
        for m in models:
            repo_id: str = m.get("id", "")
            # Normalise both for comparison: lowercase, strip common suffixes
            name_norm = cache_key.replace(":", "-").replace("/", "-")
            if name_norm in repo_id.lower() or cache_key in repo_id.lower():
                best_repo = m
                break
        if best_repo is None:
            best_repo = models[0]  # fall back to first result

        repo_id = best_repo.get("id", "")
        siblings: list[dict] = best_repo.get("siblings", [])

        # Find the best GGUF file by preferred quantization
        chosen_file: str | None = None
        chosen_size: float | None = None
        for quant in _PREFERRED_QUANTS:
            for s in siblings:
                fname: str = s.get("rfilename", "")
                if fname.endswith(".gguf") and quant in fname:
                    chosen_file = fname
                    # size in bytes → GB (may be None)
                    blob_size = s.get("size")
                    chosen_size = round(blob_size / (1024 ** 3), 1) if blob_size else None
                    break
            if chosen_file:
                break

        # If no preferred quant found, pick the first .gguf
        if not chosen_file:
            for s in siblings:
                fname = s.get("rfilename", "")
                if fname.endswith(".gguf"):
                    chosen_file = fname
                    blob_size = s.get("size")
                    chosen_size = round(blob_size / (1024 ** 3), 1) if blob_size else None
                    break

        if chosen_file:
            result = {
                "found": True,
                "hf_repo": repo_id,
                "gguf_file": chosen_file,
                "pull_command": f"docker model pull hf.co/{repo_id}",
                "size_gb": chosen_size,
            }
        else:
            result = {"found": False, "hf_repo": repo_id, "gguf_file": None, "pull_command": None, "size_gb": None}

    except Exception as exc:  # noqa: BLE001
        logger.warning("GGUF resolver failed for %r: %s", model_name, exc)
        result = {"found": False, "hf_repo": None, "gguf_file": None, "pull_command": None, "size_gb": None, "error": str(exc)}

    _gguf_cache[cache_key] = {**result, "_ts": now}
    return result

# ---------------------------------------------------------------------------
# Proactive model discovery (Ollama library + HuggingFace Hub)
# ---------------------------------------------------------------------------

_discover_cache: dict[str, object] = {}   # key → {result, "_ts"}
_DISCOVER_CACHE_TTL = 21_600             # 6 hours


@dataclass
class DiscoveredModel:
    """A model available on a public registry that the user has not yet installed."""
    name: str
    source: str           # "ollama" | "huggingface"
    size_gb: float
    fits_in_ram: bool
    task_fit: int
    description: str
    pull_count: int
    pull_command: str


# Curated static fallback catalog — used when ollama.com is unreachable (e.g. Docker).
# Format matches the Ollama search API response shape used in discover_models().
# Models are listed best-for-task first; size in bytes uses 1 GB = 1_073_741_824.
_OLLAMA_STATIC_CATALOG: list[dict] = [
    {"name": "phi4",          "description": "Microsoft Phi-4 14B — top-tier JSON extraction", "pulls": 2_000_000, "tags": [{"name": "latest", "size": 8_589_934_592}]},
    {"name": "phi4-mini",     "description": "Microsoft Phi-4 Mini 3.8B — fast, low RAM", "pulls": 3_000_000, "tags": [{"name": "latest", "size": 4_294_967_296}]},
    {"name": "qwen3:8b",      "description": "Alibaba Qwen 3 8B — excellent instruction following", "pulls": 1_500_000, "tags": [{"name": "8b",   "size": 5_368_709_120}]},
    {"name": "qwen3:14b",     "description": "Alibaba Qwen 3 14B — strong multi-language structured output", "pulls": 800_000, "tags": [{"name": "14b", "size": 9_663_676_416}]},
    {"name": "qwen3:30b-a3b", "description": "Alibaba Qwen 3 30B MoE — high accuracy, moderate RAM", "pulls": 400_000, "tags": [{"name": "latest", "size": 18_253_611_008}]},
    {"name": "qwen2.5:14b",   "description": "Alibaba Qwen 2.5 14B — proven JSON accuracy", "pulls": 2_500_000, "tags": [{"name": "14b", "size": 9_663_676_416}]},
    {"name": "qwen2.5:7b",    "description": "Alibaba Qwen 2.5 7B — best value for RAM", "pulls": 4_000_000, "tags": [{"name": "7b",  "size": 4_831_838_208}]},
    {"name": "llama3.3",      "description": "Meta Llama 3.3 70B — flagship generalist (high RAM)", "pulls": 1_000_000, "tags": [{"name": "latest", "size": 43_486_756_864}]},
    {"name": "llama3.2:3b",   "description": "Meta Llama 3.2 3B — lightweight, fast", "pulls": 5_000_000, "tags": [{"name": "3b",  "size": 2_147_483_648}]},
    {"name": "mistral-small", "description": "Mistral Small 22B — strong structured output", "pulls": 600_000, "tags": [{"name": "latest", "size": 13_421_772_800}]},
    {"name": "mistral-nemo",  "description": "Mistral NeMo 12B — good balance of speed and quality", "pulls": 800_000, "tags": [{"name": "latest", "size": 7_516_192_768}]},
    {"name": "gemma3:4b",     "description": "Google Gemma 3 4B — compact, accurate", "pulls": 2_000_000, "tags": [{"name": "4b",  "size": 3_221_225_472}]},
    {"name": "gemma3:12b",    "description": "Google Gemma 3 12B — balanced quality", "pulls": 900_000, "tags": [{"name": "12b", "size": 8_053_063_680}]},
    {"name": "deepseek-r1:7b","description": "DeepSeek R1 7B — reasoning-optimised", "pulls": 700_000, "tags": [{"name": "7b",  "size": 4_831_838_208}]},
]


def _fetch_ollama_search(limit: int = 50) -> tuple[list[dict], bool]:
    """Fetch the Ollama model library catalog.

    Returns (models_list, reachable).
    Ollama search API: GET https://ollama.com/api/search?q=&limit=N&sort=popular
    Each entry: { name, description, pulls, tags: [{name, size}], updated_at }
    Falls back to _OLLAMA_STATIC_CATALOG when the network is unreachable.
    """
    try:
        resp = _httpx.get(
            "https://ollama.com/api/search",
            params={"q": "", "limit": limit, "sort": "popular"},
            timeout=8.0,
        )
        resp.raise_for_status()
        data = resp.json()
        # API returns list directly or {"models": [...]}
        models = data if isinstance(data, list) else data.get("models", [])
        if models:
            return models, True
        # Empty response — fall back to static catalog
        logger.info("Ollama search returned empty list; using static catalog fallback")
        return _OLLAMA_STATIC_CATALOG, False
    except Exception as exc:  # noqa: BLE001
        logger.info("Ollama discovery unavailable (%s); using static catalog fallback", exc)
        return _OLLAMA_STATIC_CATALOG, False


def _fetch_hf_text_gen(limit: int = 20, hf_token: str | None = None) -> tuple[list[dict], bool]:
    """Fetch top GGUF text-generation models from HuggingFace Hub.

    Returns (models_list, reachable).
    """
    headers: dict[str, str] = {"Accept": "application/json"}
    if hf_token:
        headers["Authorization"] = f"Bearer {hf_token}"
    try:
        resp = _httpx.get(
            "https://huggingface.co/api/models",
            params={
                "task": "text-generation",
                "filter": "gguf",
                "sort": "downloads",
                "direction": -1,
                "limit": limit,
            },
            headers=headers,
            timeout=8.0,
        )
        resp.raise_for_status()
        data = resp.json()
        return (data if isinstance(data, list) else []), True
    except Exception as exc:  # noqa: BLE001
        logger.info("HuggingFace discovery unavailable: %s", exc)
        return [], False


def _score_model_name(model_name: str) -> int:
    """Score a model name for structured JSON extraction fitness (1–10).

    Three-step lookup:
    1. Exact match in _OLLAMA_TASK_FIT (handles tagged variants like qwen2.5:7b).
    2. Exact family match (strip tag, compare key families like "qwen2.5" == "qwen2.5").
    3. Prefix match via _FAMILY_PREFIX_SCORES — handles HuggingFace compound names like
       "qwen3.6-27b-mtp-gguf" → prefix "qwen3.6" → score 9.
    Finally cap specialised models (coder/embed/vision) to ≤ 4.
    """
    base = _base_name(model_name)
    base_lower = base.lower()

    # Step 1: exact lookup
    score = _OLLAMA_TASK_FIT.get(base, None)

    # Step 2: exact family match (strip tag from both sides)
    if score is None:
        family = base_lower.split(":")[0]
        for key, val in _OLLAMA_TASK_FIT.items():
            if family == key.split(":")[0]:
                score = val
                break

    # Step 3: prefix match for compound HF names — first prefix match wins
    if score is None:
        for prefix, val in _FAMILY_PREFIX_SCORES:
            if base_lower.startswith(prefix):
                score = val
                break

    score = score if score is not None else 5  # neutral default

    # Cap specialised models regardless of lookup result
    if any(base_lower.endswith(sfx) or sfx in base_lower for sfx in _SPECIALISED_SUFFIXES):
        score = min(score, 4)
    return score


def discover_models(
    installed_names: list[str],
    ram_gb: float,
    hf_token: str | None = None,
) -> tuple[list[DiscoveredModel], dict[str, bool]]:
    """Query Ollama library and HuggingFace Hub for recommended models not yet installed.

    Returns (discovered_models, sources_reachable).
    discovered_models is sorted: fits_in_ram DESC, task_fit DESC, size_gb ASC.
    Results cached for 6 hours; force-refresh by clearing _discover_cache.
    Network errors result in empty list — discovery is best-effort and must
    never break the Settings page.

    Models scoring ≤ 4 (code/embed/vision specialised) are excluded entirely.
    Max 12 results returned.
    """
    cache_key = f"discover:{round(ram_gb)}"
    now = _time.time()

    cached = _discover_cache.get(cache_key)
    if cached and now - cached["_ts"] < _DISCOVER_CACHE_TTL:  # type: ignore[index]
        return cached["models"], cached["sources_reachable"]  # type: ignore[index]

    installed_bases = {_base_name(n) for n in installed_names}

    ollama_models, ollama_ok = _fetch_ollama_search(limit=50)
    hf_models, hf_ok = _fetch_hf_text_gen(limit=20, hf_token=hf_token)
    sources_reachable = {"ollama": ollama_ok, "huggingface": hf_ok}

    seen_names: set[str] = set()
    results: list[DiscoveredModel] = []

    # ── Process Ollama library results ──────────────────────────────────────
    for m in ollama_models:
        name: str = m.get("name", "").strip()
        if not name:
            continue

        base = _base_name(name)
        # Skip already installed
        if base in installed_bases or name in installed_names:
            continue
        # Skip already in results (de-dup)
        if base in seen_names:
            continue

        score = _score_model_name(name)
        # Exclude specialised/embedding models entirely
        if score <= 4:
            continue

        # Size: use smallest tag, or look up in RAM table
        tags: list[dict] = m.get("tags", [])
        min_size_bytes = min((t.get("size", 0) for t in tags if t.get("size")), default=0)
        size_gb = round(min_size_bytes / (1024 ** 3), 1) if min_size_bytes else 0.0
        if size_gb == 0.0:
            known = _OLLAMA_RAM_GB.get(base)
            size_gb = known if known else 0.0

        fits = (ram_gb >= size_gb * 1.2) if size_gb > 0 else True

        results.append(DiscoveredModel(
            name=name,
            source="ollama",
            size_gb=size_gb,
            fits_in_ram=fits,
            task_fit=score,
            description=(m.get("description") or "")[:120],
            pull_count=m.get("pulls") or 0,
            pull_command=f"ollama pull {name}",
        ))
        seen_names.add(base)

    # ── Process HuggingFace results ─────────────────────────────────────────
    for m in hf_models:
        repo_id: str = m.get("id") or m.get("modelId") or ""
        if not repo_id:
            continue

        # Derive a simple name from the repo (e.g. "Phi-4-mini-instruct-GGUF" → "phi4-mini")
        short = repo_id.split("/")[-1].lower()

        # Skip clearly low-quality HF repo names — good model repo names are short
        # and recognizable. Long compound strings (e.g. "qwythos-9b-claude-mythos-5-1m-gguf")
        # are fine-tuned variants, not general-purpose candidates worth suggesting.
        if len(short) > 40 or short.count("-") > 4:
            continue

        # Try to match against a known name — if it's already covered by an Ollama result, skip
        if any(short.startswith(s) or s in short for s in seen_names):
            continue
        if any(_base_name(n) in short for n in installed_names):
            continue

        score = _score_model_name(short)
        if score <= 4:
            continue

        # Size from siblings
        siblings: list[dict] = m.get("siblings", [])
        gguf_sizes = [
            s.get("size", 0) for s in siblings
            if s.get("rfilename", "").endswith(".gguf") and s.get("size")
        ]
        size_bytes = min(gguf_sizes) if gguf_sizes else 0
        size_gb = round(size_bytes / (1024 ** 3), 1) if size_bytes else 0.0
        fits = (ram_gb >= size_gb * 1.2) if size_gb > 0 else True

        results.append(DiscoveredModel(
            name=short,
            source="huggingface",
            size_gb=size_gb,
            fits_in_ram=fits,
            task_fit=score,
            description="",
            pull_count=m.get("downloads") or 0,
            pull_command=f"docker model pull hf.co/{repo_id}",
        ))
        seen_names.add(short.split(":")[0])

    # Sort: fits-in-RAM first, then task_fit desc, then size asc
    results.sort(key=lambda r: (0 if r.fits_in_ram else 1, -r.task_fit, r.size_gb))
    results = results[:12]

    _discover_cache[cache_key] = {
        "models": results,
        "sources_reachable": sources_reachable,
        "_ts": now,
    }
    return results, sources_reachable
