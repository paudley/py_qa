# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Backward-compatible re-export of lint literals."""

from __future__ import annotations

from ...core import lint_literals as _core_literals

BanditLevelLiteral = _core_literals.BanditLevelLiteral
BANDIT_LEVEL_CHOICES = _core_literals.BANDIT_LEVEL_CHOICES
OUTPUT_MODE_CHOICES = _core_literals.OUTPUT_MODE_CHOICES
OUTPUT_MODE_CONCISE = _core_literals.OUTPUT_MODE_CONCISE
OutputModeLiteral = _core_literals.OutputModeLiteral
PR_SUMMARY_SEVERITIES = _core_literals.PR_SUMMARY_SEVERITIES
PRSummarySeverityLiteral = _core_literals.PRSummarySeverityLiteral
PROGRESS_EVENT_COMPLETED = _core_literals.PROGRESS_EVENT_COMPLETED
PROGRESS_EVENT_START = _core_literals.PROGRESS_EVENT_START
ProgressPhaseLiteral = _core_literals.ProgressPhaseLiteral
SENSITIVITY_CHOICES = _core_literals.SENSITIVITY_CHOICES
SensitivityLiteral = _core_literals.SensitivityLiteral
STRICTNESS_CHOICES = _core_literals.STRICTNESS_CHOICES
StrictnessLiteral = _core_literals.StrictnessLiteral

__all__ = (
    "OutputModeLiteral",
    "OUTPUT_MODE_CHOICES",
    "OUTPUT_MODE_CONCISE",
    "BanditLevelLiteral",
    "BANDIT_LEVEL_CHOICES",
    "PRSummarySeverityLiteral",
    "PR_SUMMARY_SEVERITIES",
    "ProgressPhaseLiteral",
    "PROGRESS_EVENT_COMPLETED",
    "PROGRESS_EVENT_START",
    "SensitivityLiteral",
    "SENSITIVITY_CHOICES",
    "StrictnessLiteral",
    "STRICTNESS_CHOICES",
)
