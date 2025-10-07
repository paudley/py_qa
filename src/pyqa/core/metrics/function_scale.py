# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Function scale estimation utilities shared across analysis and reporting."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from ...interfaces.analysis import FunctionScaleEstimator

_KEYWORD_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\b(if|for|while|elif|case|except|and|or|try|with)\b",
)


@dataclass(slots=True)
class FunctionScaleEstimatorService(FunctionScaleEstimator):
    """Compute approximate function size and cyclomatic complexity."""

    @property
    def supported_languages(self) -> tuple[str, ...]:
        """Return the languages supported by the estimator."""

        return ("python",)

    def estimate(self, path: Path, function: str) -> tuple[int | None, int | None]:
        """Return approximate line count and complexity for ``function``.

        Args:
            path: Filesystem path containing the function definition.
            function: Function name (without module path) to analyse.

        Returns:
            tuple[int | None, int | None]: Estimated line count and complexity
            measures, or ``None`` for values that cannot be derived.
        """

        if not function:
            return (None, None)
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return (None, None)

        lines = text.splitlines()
        signature_pattern = re.compile(rf"^\s*(?:async\s+)?def\s+{re.escape(function)}\b")
        start_index: int | None = None
        indent_level: int | None = None
        for idx, line in enumerate(lines):
            if signature_pattern.match(line):
                start_index = idx
                indent_level = len(line) - len(line.lstrip(" \t"))
                break
        if start_index is None or indent_level is None:
            return (None, None)

        line_count = 1  # include signature line
        complexity = 0
        for line in lines[start_index + 1 :]:
            stripped = line.strip()
            if not stripped:
                continue
            current_indent = len(line) - len(line.lstrip(" \t"))
            if current_indent <= indent_level:
                break
            line_count += 1
            complexity += len(_KEYWORD_PATTERN.findall(stripped))

        return (
            line_count if line_count > 0 else None,
            complexity if complexity > 0 else None,
        )


__all__ = ["FunctionScaleEstimatorService"]
