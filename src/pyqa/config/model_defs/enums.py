# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Provide shared enumeration types for configuration models."""

from __future__ import annotations

from enum import Enum


class StrictnessLevel(str, Enum):
    """Provide enumeration of supported type-checking strictness levels."""

    LENIENT = "lenient"
    STANDARD = "standard"
    STRICT = "strict"


class SensitivityLevel(str, Enum):
    """Provide enumeration of sensitivity presets available to callers."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    MAXIMUM = "maximum"


class BanditLevel(str, Enum):
    """Provide enumeration of severity levels supported by Bandit."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class BanditConfidence(str, Enum):
    """Provide enumeration of confidence levels supported by Bandit."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


__all__ = [
    "BanditConfidence",
    "BanditLevel",
    "SensitivityLevel",
    "StrictnessLevel",
]
