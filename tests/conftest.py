"""Shared pytest fixtures for RVTool Genesis integration tests."""
from __future__ import annotations

import os
import sys

import pytest
import httpx

# Ensure the api/ package is importable when pytest is run from the repo root.
# Individual test files that import directly from services.*, routers.*, etc.
# rely on this path being present.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))


@pytest.fixture(scope="session")
def base_url() -> str:
    """Base URL for the running API server.

    When running inside the Docker container (api service), the API listens on
    port 8000 at localhost.  When running from the host machine against the
    published port, the API is exposed at 8001.  The BASE_URL env var lets
    callers override the default.
    """
    import os
    return os.environ.get("BASE_URL", "http://localhost:8000")


@pytest.fixture
def test_project(base_url: str):
    """Create a test project, yield it, then delete it as cleanup."""
    resp = httpx.post(
        f"{base_url}/api/projects",
        json={"name": "Test Project (auto)", "description": "Created by pytest"},
        timeout=10,
    )
    resp.raise_for_status()
    project = resp.json()

    yield project

    # Cleanup — best-effort
    try:
        httpx.delete(f"{base_url}/api/projects/{project['id']}", timeout=10)
    except Exception:  # noqa: BLE001
        pass
