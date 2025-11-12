# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Expose configuration models governing strictness settings."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from ...model_defs import StrictnessLevel


class StrictnessConfig(BaseModel):
    """Manage type-checking strictness controls shared by tools."""

    model_config = ConfigDict(validate_assignment=True)

    type_checking: StrictnessLevel = StrictnessLevel.STANDARD


__all__ = ["StrictnessConfig"]
