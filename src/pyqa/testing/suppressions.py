# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Default warning suppressions applied to test suites per language."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Final

from pyqa.cache.in_memory import memoize

from ..catalog.metadata import catalog_test_suppressions

TestSuppressionsMap = dict[str, dict[str, tuple[str, ...]]]

_MANUAL_TEST_SUPPRESSIONS: Final[TestSuppressionsMap] = {
    "*": {
        # Ignore missing-implementation diagnostics in test suites; tests often
        # use lightweight stand-ins and assertions that intentionally raise
        # NotImplementedError as sentinels.
        "missing": (r"^missing, .*/tests/.*",),
    },
}


@memoize(maxsize=1)
def _catalog_test_suppressions() -> TestSuppressionsMap:
    """Return cached catalog suppressions grouped by language and tool.

    Returns:
        TestSuppressionsMap: Mapping of language -> tool -> suppression patterns.
    """

    catalog_map = catalog_test_suppressions()
    mapping: TestSuppressionsMap = {}
    for language, tool_map in catalog_map.items():
        mapping[language] = {tool: tuple(patterns) for tool, patterns in tool_map.items()}
    for language, tool_map in _MANUAL_TEST_SUPPRESSIONS.items():
        target = mapping.setdefault(language, {})
        for tool, patterns in tool_map.items():
            existing = list(target.get(tool, ()))
            existing.extend(patterns)
            target[tool] = tuple(dict.fromkeys(existing))
    return mapping


def flatten_test_suppressions(
    languages: Iterable[str] | None = None,
) -> dict[str, list[str]]:
    """Return a tool -> suppression-pattern mapping for the given *languages*.

    Args:
        languages: Optional iterable restricting suppressions to specific languages.

    Returns:
        dict[str, list[str]]: Mapping of tool identifiers to unique suppression patterns.
    """

    source = _catalog_test_suppressions()
    if languages is None:
        selected = set(source)
    else:
        selected = {language.lower() for language in languages if language}

    merged: dict[str, list[str]] = {}
    for language in selected:
        tool_map = source.get(language)
        if not tool_map:
            continue
        for tool, patterns in tool_map.items():
            merged.setdefault(tool, []).extend(patterns)
    return {tool: list(dict.fromkeys(patterns)) for tool, patterns in merged.items()}


__all__ = ["flatten_test_suppressions"]
