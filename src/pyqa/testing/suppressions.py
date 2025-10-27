# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Default warning suppressions applied to test suites per language."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Final

from pyqa.cache.in_memory import memoize
from pyqa.interfaces.internal_linting import INTERNAL_LINTER_TOOL_NAMES

from ..catalog.metadata import catalog_test_suppressions

TestSuppressionsMap = dict[str, dict[str, tuple[str, ...]]]
_TEST_SUPPRESSION_SUFFIX: Final[str] = r"(?:.+/)?tests?/.*$"


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
    return mapping


def build_internal_test_suppression_pattern(tool_name: str) -> str:
    """Return the canonical regex used to suppress internal lint tool tests.

    Args:
        tool_name: Name of the internal tool being suppressed.

    Returns:
        str: Regex pattern used to ignore diagnostics produced from tests.
    """

    return rf"^{re.escape(tool_name)}, {_TEST_SUPPRESSION_SUFFIX}"


_INTERNAL_SUPPRESSIONS: dict[str, tuple[str, ...]] = {
    tool: (build_internal_test_suppression_pattern(tool),) for tool in INTERNAL_LINTER_TOOL_NAMES
}


def flatten_test_suppressions(
    languages: Iterable[str] | None = None,
) -> dict[str, list[str]]:
    """Return a tool -> suppression-pattern mapping for tests and internal linters.

    Args:
        languages: Optional iterable restricting suppressions to specific languages.

    Returns:
        dict[str, list[str]]: Mapping of tool identifiers to unique suppression patterns.
    """

    source = _catalog_test_suppressions()
    selected = set(source) if languages is None else {language.lower() for language in languages if language}

    merged: dict[str, list[str]] = {}
    for language in selected:
        tool_map = source.get(language)
        if not tool_map:
            continue
        for tool, patterns in tool_map.items():
            merged.setdefault(tool, []).extend(patterns)
    for tool, patterns in _INTERNAL_SUPPRESSIONS.items():
        merged.setdefault(tool, []).extend(patterns)
    return {tool: list(dict.fromkeys(patterns)) for tool, patterns in merged.items()}


__all__ = [
    "build_internal_test_suppression_pattern",
    "flatten_test_suppressions",
]
