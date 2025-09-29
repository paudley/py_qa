"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def schema_root() -> Path:
    """Return the repository schema directory used across catalog tests."""

    return Path(__file__).resolve().parents[1] / "tooling" / "schema"
