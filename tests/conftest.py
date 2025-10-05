# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def schema_root() -> Path:
    """Return the repository schema directory used across catalog tests."""
    return Path(__file__).resolve().parents[1] / "tooling" / "schema"
# BDD fixtures auto-use the pytest-bdd plugin available via pyproject (pytest-bdd).

pytest_plugins = ["tests.wrapper.steps.cli_steps"]
