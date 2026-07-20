"""Unit tests for api/services/model_catalog.py — task-fit scoring and ranking."""
from __future__ import annotations

import sys
import os

# Ensure the api package is importable when running from the tests/ directory.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

import pytest
from services.model_catalog import rank_local_models, get_pull_suggestion, _OLLAMA_TASK_FIT


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _model(name: str, size_bytes: int = 2_000_000_000) -> dict:
    """Build a minimal Ollama /api/tags model dict."""
    return {"name": name, "size": size_bytes}


def _rank(models: list[dict], ram_gb: float = 16.0):
    return rank_local_models(models, ram_gb)


# ---------------------------------------------------------------------------
# 1. Code-specialised models score low (≤ 4) and lose to phi4-mini
# ---------------------------------------------------------------------------

class TestCodeModelsScoreLow:
    def test_qwen_coder_1_5b_below_phi4_mini(self):
        """qwen2.5-coder:1.5b must rank below phi4-mini."""
        results = _rank([
            _model("phi4-mini:latest"),
            _model("qwen2.5-coder:1.5b"),
        ])
        names = [r.name for r in results]
        assert names.index("phi4-mini:latest") < names.index("qwen2.5-coder:1.5b"), (
            f"Expected phi4-mini before qwen2.5-coder, got order: {names}"
        )

    def test_qwen_coder_task_fit_at_most_4(self):
        """All qwen2.5-coder variants must have task_fit ≤ 4."""
        coder_models = [
            "qwen2.5-coder:1.5b",
            "qwen2.5-coder:7b",
            "qwen2.5-coder:14b",
            "qwen2.5-coder:32b",
        ]
        results = _rank([_model(m) for m in coder_models])
        for r in results:
            assert r.task_fit <= 4, (
                f"{r.name} has task_fit {r.task_fit}, expected ≤ 4"
            )

    def test_codellama_scores_low(self):
        results = _rank([_model("codellama:latest")])
        assert results[0].task_fit <= 4

    def test_deepseek_coder_scores_low(self):
        results = _rank([_model("deepseek-coder:latest")])
        assert results[0].task_fit <= 4

    def test_starcoder_scores_low(self):
        results = _rank([_model("starcoder:latest")])
        assert results[0].task_fit <= 4

    def test_codegemma_scores_low(self):
        results = _rank([_model("codegemma:latest")])
        assert results[0].task_fit <= 4


# ---------------------------------------------------------------------------
# 2. Embedding models score 1–2 and rank last
# ---------------------------------------------------------------------------

class TestEmbeddingModelsRankLast:
    def test_nomic_embed_ranks_last(self):
        """nomic-embed-text must rank below any generalist model."""
        results = _rank([
            _model("phi4-mini:latest"),
            _model("nomic-embed-text:latest"),
        ])
        assert results[-1].name == "nomic-embed-text:latest", (
            f"Expected nomic-embed-text last, got: {[r.name for r in results]}"
        )

    def test_embedding_models_score_at_most_2(self):
        embed_models = [
            "nomic-embed-text:latest",
            "mxbai-embed-large:latest",
            "all-minilm:latest",
        ]
        results = _rank([_model(m) for m in embed_models])
        for r in results:
            assert r.task_fit <= 2, f"{r.name} has task_fit {r.task_fit}, expected ≤ 2"


# ---------------------------------------------------------------------------
# 3. phi4-mini is recommended when installed alongside qwen2.5-coder
# ---------------------------------------------------------------------------

class TestPhi4MiniRecommended:
    def test_phi4_mini_recommended_over_coder(self):
        results = _rank([
            _model("phi4-mini:latest"),
            _model("qwen2.5-coder:1.5b"),
        ])
        recommended = [r for r in results if r.recommended]
        assert len(recommended) == 1
        assert recommended[0].name == "phi4-mini:latest", (
            f"Expected phi4-mini recommended, got: {recommended[0].name}"
        )

    def test_phi4_mini_recommended_over_embed(self):
        results = _rank([
            _model("phi4-mini:latest"),
            _model("nomic-embed-text:latest"),
        ])
        recommended = [r for r in results if r.recommended]
        assert recommended[0].name == "phi4-mini:latest"


# ---------------------------------------------------------------------------
# 4. get_pull_suggestion returns None when phi4-mini is installed
# ---------------------------------------------------------------------------

class TestPullSuggestion:
    def test_no_suggestion_when_phi4_mini_installed(self):
        result = get_pull_suggestion(["phi4-mini:latest"], ram_gb=16.0)
        assert result is None, (
            f"Expected no pull suggestion with phi4-mini installed, got: {result}"
        )

    def test_suggestion_returned_when_only_coder_installed(self):
        """With only a coder model installed, a generalist should be suggested."""
        result = get_pull_suggestion(["qwen2.5-coder:1.5b"], ram_gb=16.0)
        assert result is not None, "Expected a pull suggestion when only coder model installed"
        assert result["model"] in ("phi4-mini", "phi4", "qwen2.5:7b", "qwen2.5:14b")


# ---------------------------------------------------------------------------
# 5. Unknown model without specialised suffix gets a neutral score (5)
# ---------------------------------------------------------------------------

class TestUnknownModelDefault:
    def test_unknown_generic_model_scores_5(self):
        results = _rank([_model("some-unknown-model:latest")])
        assert results[0].task_fit == 5, (
            f"Expected unknown model to score 5, got {results[0].task_fit}"
        )

    def test_unknown_coder_model_capped_at_4(self):
        """An unknown model with '-coder' in the name must be capped at 4."""
        results = _rank([_model("new-coder-model:latest")])
        assert results[0].task_fit <= 4, (
            f"Expected unknown coder model to be capped at ≤ 4, got {results[0].task_fit}"
        )
