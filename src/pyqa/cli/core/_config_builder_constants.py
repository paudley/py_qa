# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Constant values and enumerations shared across config builder helpers."""

from __future__ import annotations

from collections.abc import Iterable
from enum import Enum
from pathlib import Path
from typing import Final, Literal

from ...catalog.metadata import catalog_general_suppressions
from ...testing.suppressions import flatten_test_suppressions


class LintOptionKey(str, Enum):
    """Enumerate CLI option identifiers used for configuration overrides."""

    SENSITIVITY = "sensitivity"
    MAX_COMPLEXITY = "max_complexity"
    MAX_ARGUMENTS = "max_arguments"
    TYPE_CHECKING = "type_checking"
    BANDIT_SEVERITY = "bandit_severity"
    BANDIT_CONFIDENCE = "bandit_confidence"
    PYLINT_FAIL_UNDER = "pylint_fail_under"
    PATHS_FROM_STDIN = "paths_from_stdin"
    CHANGED_ONLY = "changed_only"
    DIFF_REF = "diff_ref"
    INCLUDE_UNTRACKED = "include_untracked"
    BASE_BRANCH = "base_branch"
    DIRS = "dirs"
    PATHS = "paths"
    EXCLUDE = "exclude"
    INCLUDE_DOTFILES = "include_dotfiles"
    FILTERS = "filters"
    VERBOSE = "verbose"
    QUIET = "quiet"
    NO_COLOR = "no_color"
    NO_EMOJI = "no_emoji"
    OUTPUT_MODE = "output_mode"
    SHOW_PASSING = "show_passing"
    NO_STATS = "no_stats"
    ADVICE = "advice"
    PR_SUMMARY_OUT = "pr_summary_out"
    PR_SUMMARY_LIMIT = "pr_summary_limit"
    PR_SUMMARY_MIN_SEVERITY = "pr_summary_min_severity"
    PR_SUMMARY_TEMPLATE = "pr_summary_template"
    ONLY = "only"
    LANGUAGE = "language"
    FIX_ONLY = "fix_only"
    CHECK_ONLY = "check_only"
    BAIL = "bail"
    JOBS = "jobs"
    NO_CACHE = "no_cache"
    CACHE_DIR = "cache_dir"
    USE_LOCAL_LINTERS = "use_local_linters"
    LINE_LENGTH = "line_length"
    SQL_DIALECT = "sql_dialect"
    PYTHON_VERSION = "python_version"


FILTER_SPEC_SEPARATOR: Final[str] = ":"
FILTER_PATTERN_SEPARATOR: Final[str] = ";;"
FILTER_SPEC_FORMAT: Final[str] = "TOOL:regex"


OutputMode = Literal["concise", "pretty", "raw"]
SummarySeverity = Literal["error", "warning", "notice", "note"]

_ALLOWED_OUTPUT_MODES: Final[tuple[OutputMode, ...]] = ("concise", "pretty", "raw")
_ALLOWED_SUMMARY_SEVERITIES: Final[tuple[SummarySeverity, ...]] = (
    "error",
    "warning",
    "notice",
    "note",
)


_BASE_TOOL_FILTERS: Final[dict[str, list[str]]] = {
    "bandit": [
        r"^Run started:.*$",
        r"^Test results:$",
        r"^No issues identified\.$",
        r"^Files skipped \(.*\):$",
    ],
    "black": [
        r"^All done! [0-9]+ files? (re)?formatted\.$",
        r"^All done! ✨ .* files? left unchanged\.$",
    ],
    "isort": [
        r"^SUCCESS: .* files? are correctly sorted and formatted\.$",
        r"^Nothing to do\.$",
    ],
    "mypy": [r"^Success:.*"],
    "pylint": [
        r"^Your code has been rated at 10\.00/10.*$",
        r"^----",
        r"^Your code has been rated",
        r"^$",
        r"^\*\*\*",
    ],
    "pyright": [
        r"^No configuration file found\..*",
        r"^No pyright configuration found\..*",
        r"^0 errors, 0 warnings, 0 informations$",
        r"^Found 0 errors in .* files? \(.*\)$",
    ],
    "pytest": [
        r"^=+ .* in .*s =+$",
        r"^collected \[0-9]+ items$",
        r"^platform .* - Python .*",
        r"^cache cleared$",
    ],
    "ruff": [
        r"^Found 0 errors\..*$",
        r"^All checks passed!$",
        r"^.* 0 files? reformatted.*$",
    ],
    "vulture": [r"^No dead code found$"],
}


def build_default_tool_filters() -> dict[str, list[str]]:
    """Return merged default tool filters with catalog and test suppressions.

    Returns:
        dict[str, list[str]]: Mapping of tool identifiers to filtered console noise patterns.
    """

    merged: dict[str, list[str]] = {tool: list(patterns) for tool, patterns in _BASE_TOOL_FILTERS.items()}
    for tool, test_patterns in flatten_test_suppressions().items():
        _extend_filter_patterns(merged, tool, test_patterns)
    for tool, catalog_patterns in catalog_general_suppressions().items():
        _extend_filter_patterns(merged, tool, catalog_patterns)
    deduped: dict[str, list[str]] = {}
    for tool, patterns in merged.items():
        seen: set[str] = set()
        unique_patterns: list[str] = []
        for pattern in patterns:
            if pattern not in seen:
                seen.add(pattern)
                unique_patterns.append(pattern)
        deduped[tool] = unique_patterns
    return deduped


def _extend_filter_patterns(
    target: dict[str, list[str]],
    tool: str,
    patterns: Iterable[str],
) -> None:
    """Extend ``target`` with patterns for ``tool`` while preserving typing.

    Args:
        target: Mapping of tool identifiers to mutable filter lists.
        tool: Tool identifier associated with the pattern sequence.
        patterns: Iterable of patterns destined for the tool entry.

    """

    additions = [pattern for pattern in patterns if pattern]
    if not additions:
        return
    if tool in target:
        target[tool].extend(additions)
    else:
        target[tool] = additions


DEFAULT_TOOL_FILTERS: Final[dict[str, list[str]]] = build_default_tool_filters()

DEFAULT_EXCLUDES: Final[tuple[Path, ...]] = (
    Path(".venv"),
    Path(".git"),
    Path("build"),
    Path("dist"),
    Path(".mypy_cache"),
    Path(".ruff_cache"),
    Path(".pytest_cache"),
    Path(".tox"),
    Path(".eggs"),
    Path(".lint-cache"),
    Path(".cache"),
    Path(".aider.chat.history.md"),
    Path("src/.lint-cache"),
)

# Section keys used when constructing configuration payloads
FILE_DISCOVERY_SECTION: Final[str] = "file_discovery"
OUTPUT_SECTION: Final[str] = "output"
EXECUTION_SECTION: Final[str] = "execution"
DEDUPE_SECTION: Final[str] = "dedupe"
SEVERITY_RULES_KEY: Final[str] = "severity_rules"
TOOL_SETTINGS_KEY: Final[str] = "tool_settings"


__all__ = [
    "LintOptionKey",
    "FILTER_SPEC_SEPARATOR",
    "FILTER_PATTERN_SEPARATOR",
    "FILTER_SPEC_FORMAT",
    "OutputMode",
    "SummarySeverity",
    "_ALLOWED_OUTPUT_MODES",
    "_ALLOWED_SUMMARY_SEVERITIES",
    "DEFAULT_TOOL_FILTERS",
    "DEFAULT_EXCLUDES",
    "FILE_DISCOVERY_SECTION",
    "OUTPUT_SECTION",
    "EXECUTION_SECTION",
    "DEDUPE_SECTION",
    "SEVERITY_RULES_KEY",
    "TOOL_SETTINGS_KEY",
]
