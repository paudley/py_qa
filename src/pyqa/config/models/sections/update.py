# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Expose configuration models for dependency update workflows."""

from __future__ import annotations

from typing import Final

from pydantic import BaseModel, ConfigDict, Field

DEFAULT_UPDATE_SKIP_PATTERNS: Final[list[str]] = ["pyreadstat", ".git/modules"]


class UpdateConfig(BaseModel):
    """Manage inputs for dependency update commands."""

    model_config = ConfigDict(validate_assignment=True)

    skip_patterns: list[str] = Field(default_factory=lambda: list(DEFAULT_UPDATE_SKIP_PATTERNS))
    enabled_managers: list[str] = Field(default_factory=list)


__all__ = ["DEFAULT_UPDATE_SKIP_PATTERNS", "UpdateConfig"]
