# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Expose quality enforcement configuration models and defaults."""

from __future__ import annotations

from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

DEFAULT_QUALITY_CHECKS: Final[list[str]] = ["license", "file-size", "schema", "python"]
DEFAULT_SCHEMA_TARGETS: Final[list[Path]] = [Path("ref_docs/tool-schema.json")]
DEFAULT_PROTECTED_BRANCHES: Final[list[str]] = ["main", "master"]


class QualityConfigSection(BaseModel):
    """Manage shared quality enforcement settings."""

    model_config = ConfigDict(validate_assignment=True)

    checks: list[str] = Field(default_factory=lambda: list(DEFAULT_QUALITY_CHECKS))
    skip_globs: list[str] = Field(default_factory=list)
    schema_targets: list[Path] = Field(default_factory=lambda: list(DEFAULT_SCHEMA_TARGETS))
    warn_file_size: int = 5 * 1024 * 1024
    max_file_size: int = 10 * 1024 * 1024
    protected_branches: list[str] = Field(default_factory=lambda: list(DEFAULT_PROTECTED_BRANCHES))
    enforce_in_lint: bool = False


__all__ = [
    "DEFAULT_PROTECTED_BRANCHES",
    "DEFAULT_QUALITY_CHECKS",
    "DEFAULT_SCHEMA_TARGETS",
    "QualityConfigSection",
]
