# SPDX-License-Identifier: MIT
"""Dataclasses describing hook installation outcomes."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class InstallResult:
    """Aggregate outcome from attempting to install git hooks."""

    installed: list[Path]
    skipped: list[Path]
    backups: list[Path]


__all__ = ["InstallResult"]
