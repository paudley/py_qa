# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Default warning suppressions applied to test suites per language."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Final

TestSuppressionsMap = dict[str, dict[str, tuple[str, ...]]]

_TEST_SUPPRESSIONS: Final[TestSuppressionsMap] = {
    "python": {
        "pylint": (
            r"^pylint, (?:.+/)?tests?/.*:.*W0212.*Access to a protected member .*$",
            r"^pylint, (?:.+/)?tests?/.*:.*W0613.*Unused argument .*$",
            r"^pylint, (?:.+/)?tests?/.*:.*R2004.*$",
            r"^pylint, (?:.+/)?tests?/.*:.*magic-value-comparison.*$",
            r"^pylint, (?:.+/)?tests?/.*:.*protected-access.*$",
            r"^pylint, (?:.+/)?tests?/.*:.*unused-argument.*$",
        ),
        "mypy": (
            r"^mypy, (?:.+/)?tests?/.*:.*no-untyped-def.*$",
            r"^mypy, (?:.+/)?tests?/.*:.*attr-defined.*$",
        ),
        "ruff": (
            r"^ruff, (?:.+/)?tests?/.*:.*S101.*$",
            r"^ruff, (?:.+/)?tests?/.*:.*D103.*$",
            r"^ruff, (?:.+/)?tests?/.*:.*PT018.*$",
            r"^ruff, (?:.+/)?tests?/.*:.*ANN003.*$",
            r"^ruff, (?:.+/)?tests?/.*:.*PLR2004.*$",
            r"^ruff, (?:.+/)?tests?/.*:.*ARG001.*$",
        ),
    },
}


def flatten_test_suppressions(
    languages: Iterable[str] | None = None,
) -> dict[str, list[str]]:
    """Return a tool -> suppression-pattern mapping for the given *languages*."""
    if languages is None:
        selected = set(_TEST_SUPPRESSIONS)
    else:
        selected = {language.lower() for language in languages if language}

    merged: dict[str, list[str]] = {}
    for language in selected:
        tool_map = _TEST_SUPPRESSIONS.get(language)
        if not tool_map:
            continue
        for tool, patterns in tool_map.items():
            merged.setdefault(tool, []).extend(patterns)
    return {tool: list(dict.fromkeys(patterns)) for tool, patterns in merged.items()}


__all__ = ["flatten_test_suppressions"]
