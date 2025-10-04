# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Default warning suppressions applied to test suites per language."""

from __future__ import annotations

from collections.abc import Iterable
from functools import lru_cache

from ..tools.catalog_metadata import catalog_test_suppressions

TestSuppressionsMap = dict[str, dict[str, tuple[str, ...]]]


@lru_cache(maxsize=1)
def _catalog_test_suppressions() -> TestSuppressionsMap:
    catalog_map = catalog_test_suppressions()
    mapping: TestSuppressionsMap = {}
    for language, tool_map in catalog_map.items():
        mapping[language] = {tool: tuple(patterns) for tool, patterns in tool_map.items()}
    return mapping


def flatten_test_suppressions(
    languages: Iterable[str] | None = None,
) -> dict[str, list[str]]:
    """Return a tool -> suppression-pattern mapping for the given *languages*."""
    source = _catalog_test_suppressions()
    selected = set(source) if languages is None else {language.lower() for language in languages if language}

    merged: dict[str, list[str]] = {}
    for language in selected:
        tool_map = source.get(language)
        if not tool_map:
            continue
        for tool, patterns in tool_map.items():
            merged.setdefault(tool, []).extend(patterns)
    return {tool: list(dict.fromkeys(patterns)) for tool, patterns in merged.items()}


__all__ = ["flatten_test_suppressions"]
