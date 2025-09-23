# SPDX-License-Identifier: MIT
"""Default warning suppressions applied to test suites per language."""

from __future__ import annotations

from typing import Final, Iterable

TestSuppressionsMap = dict[str, dict[str, tuple[str, ...]]]

_TEST_SUPPRESSIONS: Final[TestSuppressionsMap] = {
    "python": {
        "pylint": (r"^(?:.+/)?tests?/.*:\d+: W0212: Access to a protected member .*$",),
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
