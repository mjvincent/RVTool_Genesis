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
from dataclasses import dataclass, field
from typing import Any

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
# Higher = better. Models not listed default to 1.
_OLLAMA_TASK_FIT: dict[str, int] = {
    "phi4":           10,
    "phi4-mini":       9,
    "qwen2.5":         9,
    "qwen2.5:7b":      9,
    "qwen2.5:14b":    10,
    "qwen2.5:32b":    10,
    "llama3.1":        7,
    "llama3.2":        7,
    "llama3.3":        8,
    "mistral":         7,
    "mistral-nemo":    8,
    "gemma2":          6,
    "gemma3":          7,
}

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
        task_fit = _OLLAMA_TASK_FIT.get(base, 1)
        # Also try matching just the family prefix (e.g. "qwen2.5" from "qwen2.5:14b")
        if task_fit == 1:
            for key, score in _OLLAMA_TASK_FIT.items():
                if base.startswith(key) or key.startswith(base.split(":")[0]):
                    task_fit = score
                    break

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
    # Check if any installed model already has high task fit
    for base in installed_bases:
        fit = _OLLAMA_TASK_FIT.get(base, 1)
        if fit >= 8:
            return None  # already have a good one

    # Suggest the best model that fits in available RAM
    for suggestion in _PULL_SUGGESTIONS:
        if ram_gb >= suggestion["min_ram_gb"]:
            return suggestion

    return None
