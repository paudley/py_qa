# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Dataclasses representing lint CLI toggle groupings."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class LintDisplayOptions:
    """Capture console toggles derived from CLI output flags."""

    no_emoji: bool
    quiet: bool
    verbose: bool
    debug: bool


@dataclass(slots=True)
class LintOutputToggles:
    """Boolean toggles controlling stdout rendering preferences."""

    verbose: bool
    quiet: bool
    no_color: bool
    no_emoji: bool
    debug: bool


__all__ = [
    "LintDisplayOptions",
    "LintOutputToggles",
]
