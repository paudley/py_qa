# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Helpers for recording analysis-layer warnings in run results."""

from __future__ import annotations

from typing import cast

from ..core.models import JsonValue, RunResult

WARNING_KEY = "warnings"
FAILURE_KEY = "aux_tool_failures"


def record_tool_warning(result: RunResult, message: str) -> None:
    """Attach a warning message to ``result`` and adjust failure metrics.

    Args:
        result: Run outcome whose ``analysis`` metadata should be updated.
        message: Warning message recorded for later presentation.
    """

    warnings_value: JsonValue = result.analysis.get(WARNING_KEY, [])
    if isinstance(warnings_value, list):
        warnings = [str(item) for item in warnings_value]
    else:
        warnings = []

    if message in warnings:
        result.analysis[WARNING_KEY] = cast(JsonValue, list(warnings))
        return

    warnings.append(message)
    result.analysis[WARNING_KEY] = cast(JsonValue, list(warnings))

    failure_value = result.analysis.get(FAILURE_KEY)
    failure_count = 0
    if isinstance(failure_value, (int, float)):
        failure_count = int(failure_value)
    elif isinstance(failure_value, str):
        try:
            failure_count = int(failure_value.strip())
        except ValueError:
            failure_count = 0
    result.analysis[FAILURE_KEY] = failure_count + 1


__all__ = ["record_tool_warning"]
