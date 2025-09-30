# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Reusable helpers for computing per-file lint metrics."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .filesystem.paths import normalise_path_key, normalize_path_key


@dataclass(slots=True)
class FileMetrics:
    """Lightweight container for line counts and suppression totals."""

    line_count: int = 0
    suppressions: dict[str, int] = field(default_factory=dict)

    def to_payload(self) -> dict[str, object]:
        return {
            "line_count": self.line_count,
            "suppressions": dict(self.suppressions),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, object] | None) -> FileMetrics:
        if not isinstance(payload, dict):
            return cls()
        raw_line = payload.get("line_count", 0)
        if isinstance(raw_line, (int, float, str)):
            try:
                line_count = int(raw_line)
            except ValueError:
                line_count = 0
        else:
            line_count = 0
        raw_suppressions = payload.get("suppressions", {})
        suppressions: dict[str, int] = dict.fromkeys(SUPPRESSION_LABELS, 0)
        if isinstance(raw_suppressions, dict):
            for label, value in raw_suppressions.items():
                if isinstance(value, (int, float, str)):
                    try:
                        suppressions[label] = int(value)
                    except ValueError:
                        suppressions[label] = 0
                else:
                    suppressions[label] = 0
        return cls(line_count=line_count, suppressions=suppressions)

    def ensure_labels(self) -> None:
        for label in SUPPRESSION_LABELS:
            self.suppressions.setdefault(label, 0)


_SUPPRESSION_PATTERNS_RAW: tuple[tuple[str, str], ...] = (
    ("noqa", r"#\s*noqa\b"),
    ("pylint", r"#\s*pylint(?::|\s)"),
    ("mypy", r"#\s*type:\s*ignore\b"),
    ("nosec", r"#\s*nosec\b"),
)
SUPPRESSION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (label, re.compile(pattern, re.IGNORECASE)) for label, pattern in _SUPPRESSION_PATTERNS_RAW
)
SUPPRESSION_LABELS: tuple[str, ...] = tuple(label for label, _ in SUPPRESSION_PATTERNS)


def compute_file_metrics(path: Path) -> FileMetrics:
    """Return :class:`FileMetrics` for ``path``, handling unreadable files."""
    metrics = FileMetrics(line_count=0, suppressions=dict.fromkeys(SUPPRESSION_LABELS, 0))
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return metrics
    lines = text.splitlines()
    metrics.line_count = len(lines)
    for line in lines:
        for label, pattern in SUPPRESSION_PATTERNS:
            if pattern.search(line):
                metrics.suppressions[label] += 1
    return metrics


__all__ = [
    "SUPPRESSION_LABELS",
    "SUPPRESSION_PATTERNS",
    "FileMetrics",
    "compute_file_metrics",
    "normalise_path_key",
    "normalize_path_key",
]
