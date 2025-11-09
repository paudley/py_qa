# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Shared type aliases used across linting interfaces."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Literal, TypeAlias

LintOptionValue: TypeAlias = bool | int | float | str | Path | None | Sequence[str] | Sequence[Path]
OutputModeLiteral: TypeAlias = Literal["concise", "pretty", "raw"]
PRSummarySeverityLiteral: TypeAlias = Literal["error", "warning", "notice", "note"]

__all__ = [
    "LintOptionValue",
    "OutputModeLiteral",
    "PRSummarySeverityLiteral",
]
