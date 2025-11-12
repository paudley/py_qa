# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Core configuration constants."""

from __future__ import annotations

from typing import Final

PYQA_LINT_DIR_NAME: Final[str] = "pyqa_lint"

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
    PYQA_LINT_DIR_NAME,
}

__all__ = ["ALWAYS_EXCLUDE_DIRS", "PYQA_LINT_DIR_NAME"]
