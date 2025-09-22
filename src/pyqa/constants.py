# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Shared constants used across pyqa modules."""

from __future__ import annotations

from typing import Final

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
    ".tool-cache",
    ".cache",
}

LANGUAGE_EXTENSIONS: Final[dict[str, set[str]]] = {
    "python": {".py", ".pyi"},
    "javascript": {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"},
    "go": {".go"},
    "rust": {".rs"},
    "markdown": {".md", ".mdx", ".markdown"},
}

LANGUAGE_MARKERS: Final[dict[str, set[str]]] = {
    "python": {
        "pyproject.toml",
        "setup.cfg",
        "requirements.txt",
        "pipfile",
        "poetry.lock",
    },
    "javascript": {
        "package.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "pnpm-workspace.yaml",
        "tsconfig.json",
    },
    "go": {"go.mod"},
    "rust": {"Cargo.toml"},
}
