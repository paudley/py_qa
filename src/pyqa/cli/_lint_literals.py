# SPDX-License-Identifier: MIT
"""Shared literal definitions for lint CLI option types.

These literals centralise the canonical vocabulary used throughout the lint
command so that both the CLI option dataclasses and Typer dependency models can
reference the same definitions without introducing circular imports.
"""

from __future__ import annotations

from typing import Final, Literal

StrictnessLiteral = Literal["lenient", "standard", "strict"]
BanditLevelLiteral = Literal["low", "medium", "high"]
SensitivityLiteral = Literal["low", "medium", "high", "maximum"]
OutputModeLiteral = Literal["concise", "pretty", "raw"]
PRSummarySeverityLiteral = Literal["error", "warning", "notice", "note"]
ProgressPhaseLiteral = Literal["start", "completed", "error"]

STRICTNESS_CHOICES: Final[tuple[StrictnessLiteral, ...]] = ("lenient", "standard", "strict")
BANDIT_LEVEL_CHOICES: Final[tuple[BanditLevelLiteral, ...]] = ("low", "medium", "high")
SENSITIVITY_CHOICES: Final[tuple[SensitivityLiteral, ...]] = (
    "low",
    "medium",
    "high",
    "maximum",
)
OUTPUT_MODE_CHOICES: Final[tuple[OutputModeLiteral, ...]] = ("concise", "pretty", "raw")
OUTPUT_MODE_CONCISE: Final[OutputModeLiteral] = "concise"
PR_SUMMARY_SEVERITIES: Final[tuple[PRSummarySeverityLiteral, ...]] = (
    "error",
    "warning",
    "notice",
    "note",
)
PROGRESS_EVENT_START: Final[ProgressPhaseLiteral] = "start"
PROGRESS_EVENT_COMPLETED: Final[ProgressPhaseLiteral] = "completed"

__all__ = [
    "BanditLevelLiteral",
    "BANDIT_LEVEL_CHOICES",
    "OUTPUT_MODE_CHOICES",
    "OUTPUT_MODE_CONCISE",
    "OutputModeLiteral",
    "PR_SUMMARY_SEVERITIES",
    "PRSummarySeverityLiteral",
    "PROGRESS_EVENT_COMPLETED",
    "PROGRESS_EVENT_START",
    "ProgressPhaseLiteral",
    "SENSITIVITY_CHOICES",
    "SensitivityLiteral",
    "STRICTNESS_CHOICES",
    "StrictnessLiteral",
]
