# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Expose repository cleanup configuration models and defaults."""

from __future__ import annotations

from typing import Final

from pydantic import BaseModel, ConfigDict, Field

DEFAULT_CLEAN_PATTERNS: Final[list[str]] = [
    "*.log",
    ".*cache",
    ".claude*.json",
    ".coverage",
    ".hypothesis",
    ".stream*.json",
    ".venv",
    "__pycache__",
    "chroma*db",
    "coverage*",
    "dist",
    "filesystem_store",
    "htmlcov*",
]

DEFAULT_CLEAN_TREES: Final[list[str]] = ["examples", "packages", "build"]


class CleanConfig(BaseModel):
    """Manage cleanup operations applied to the repository."""

    model_config = ConfigDict(validate_assignment=True)

    patterns: list[str] = Field(default_factory=lambda: list(DEFAULT_CLEAN_PATTERNS))
    trees: list[str] = Field(default_factory=lambda: list(DEFAULT_CLEAN_TREES))


__all__ = ["CleanConfig", "DEFAULT_CLEAN_PATTERNS", "DEFAULT_CLEAN_TREES"]
