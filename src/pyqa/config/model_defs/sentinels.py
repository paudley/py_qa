# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Define sentinel values used by configuration models."""

from __future__ import annotations

from enum import Enum
from typing import Final


class ConfigSentinel(str, Enum):
    """Provide enumeration of sentinels distinguishing unset configuration states."""

    UNSET = "UNSET"
    NO_BASELINE = "NO_BASELINE"


UNSET: Final[ConfigSentinel] = ConfigSentinel.UNSET
NO_BASELINE: Final[ConfigSentinel] = ConfigSentinel.NO_BASELINE

__all__ = ["ConfigSentinel", "NO_BASELINE", "UNSET"]
