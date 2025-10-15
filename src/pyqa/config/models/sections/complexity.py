# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Expose shared complexity-related configuration models."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ComplexityConfig(BaseModel):
    """Manage complexity thresholds applied to compatible tools."""

    model_config = ConfigDict(validate_assignment=True)

    max_complexity: int | None = 10
    max_arguments: int | None = 5


__all__ = ["ComplexityConfig"]
