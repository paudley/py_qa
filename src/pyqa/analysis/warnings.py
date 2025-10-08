# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Helpers for recording analysis-layer warnings in run results."""

from __future__ import annotations

from ..core.models import RunResult


def record_tool_warning(result: RunResult, message: str) -> None:
    """Attach a warning to the run result and bump auxiliary failure counters."""

    warnings = result.analysis.setdefault("warnings", [])
    if message not in warnings:
        warnings.append(message)
        result.analysis["aux_tool_failures"] = int(result.analysis.get("aux_tool_failures", 0)) + 1


__all__ = ["record_tool_warning"]
