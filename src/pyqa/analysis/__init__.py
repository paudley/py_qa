# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Higher-level analysis passes that enrich diagnostics with metadata."""

from .change_impact import apply_change_impact
from .navigator import build_refactor_navigator
from .suppression import apply_suppression_hints

__all__ = [
    "apply_change_impact",
    "apply_suppression_hints",
    "build_refactor_navigator",
]
