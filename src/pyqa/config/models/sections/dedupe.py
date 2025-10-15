# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Expose configuration models for deduplicating diagnostics."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DedupeConfig(BaseModel):
    """Manage deduplication heuristics applied to tool diagnostics."""

    model_config = ConfigDict(validate_assignment=True)

    dedupe: bool = False
    dedupe_by: Literal["first", "severity", "prefer"] = "first"
    dedupe_prefer: list[str] = Field(default_factory=list)
    dedupe_line_fuzz: int = 2
    dedupe_same_file_only: bool = True


__all__ = ["DedupeConfig"]
