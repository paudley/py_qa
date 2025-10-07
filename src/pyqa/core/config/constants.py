# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Core configuration constants."""

from __future__ import annotations

from typing import Final

PY_QA_DIR_NAME: Final[str] = "py_qa"

ALWAYS_EXCLUDE_DIRS: Final[set[str]] = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".tox",
    "coverage",
    ".lint-cache",
    ".cache",
    PY_QA_DIR_NAME,
}

__all__ = ["ALWAYS_EXCLUDE_DIRS", "PY_QA_DIR_NAME"]
