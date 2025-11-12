# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Expose shared severity configuration models."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from ...model_defs import BanditConfidence, BanditLevel, SensitivityLevel


class SeverityConfig(BaseModel):
    """Manage severity thresholds applied across multiple tools."""

    model_config = ConfigDict(validate_assignment=True)

    bandit_level: BanditLevel = BanditLevel.MEDIUM
    bandit_confidence: BanditConfidence = BanditConfidence.MEDIUM
    pylint_fail_under: float | None = 9.5
    max_warnings: int | None = None
    sensitivity: SensitivityLevel = SensitivityLevel.MEDIUM


__all__ = ["SeverityConfig"]
