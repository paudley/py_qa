# SPDX-License-Identifier: MIT
"""Helpers for constructing output configuration overrides."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path
from typing import TypedDict, cast

from ..config import OutputConfig
from ._config_builder_constants import (
    FILTER_PATTERN_SEPARATOR,
    FILTER_SPEC_FORMAT,
    FILTER_SPEC_SEPARATOR,
    LintOptionKey,
    OutputMode,
    SummarySeverity,
    _ALLOWED_OUTPUT_MODES,
    _ALLOWED_SUMMARY_SEVERITIES,
    DEFAULT_TOOL_FILTERS,
)
from ._config_builder_shared import resolve_optional_path, select_flag, select_value
from .options import LintOptions, ToolFilters


class OutputOverrides(TypedDict):
    """Mapping of output override fields."""

    tool_filters: ToolFilters
    verbose: bool
    quiet: bool
    color: bool
    emoji: bool
    output: str
    show_passing: bool
    show_stats: bool
    advice: bool
    pr_summary_out: Path | None
    pr_summary_limit: int
    pr_summary_min_severity: str
    pr_summary_template: str


def apply_output_overrides(
    current: OutputConfig,
    overrides: OutputOverrides,
) -> OutputConfig:
    """Return ``current`` updated with the supplied override mapping."""

    return current.model_copy(update=dict(overrides), deep=True)


def collect_output_overrides(
    current: OutputConfig,
    options: LintOptions,
    project_root: Path,
    has_option: Callable[[LintOptionKey], bool],
) -> OutputOverrides:
    """Return the output overrides derived from CLI inputs."""

    provided = options.provided
    tool_filters = resolve_tool_filters(
        current.tool_filters,
        DEFAULT_TOOL_FILTERS,
        options,
        has_option,
    )

    quiet_value = select_flag(options.quiet, current.quiet, LintOptionKey.QUIET, provided)
    show_passing_value = select_flag(
        options.show_passing,
        current.show_passing,
        LintOptionKey.SHOW_PASSING,
        provided,
    )
    show_stats_value = select_flag(
        not options.no_stats,
        current.show_stats,
        LintOptionKey.NO_STATS,
        provided,
    )
    if quiet_value:
        show_passing_value = False
        show_stats_value = False

    overrides: OutputOverrides = {
        "tool_filters": tool_filters,
        "verbose": select_flag(
            options.verbose,
            current.verbose,
            LintOptionKey.VERBOSE,
            provided,
        ),
        "quiet": quiet_value,
        "color": select_flag(
            not options.no_color,
            current.color,
            LintOptionKey.NO_COLOR,
            provided,
        ),
        "emoji": select_flag(
            not options.no_emoji,
            current.emoji,
            LintOptionKey.NO_EMOJI,
            provided,
        ),
        "output": (
            normalize_output_mode(options.output_mode)
            if has_option(LintOptionKey.OUTPUT_MODE)
            else current.output
        ),
        "show_passing": show_passing_value,
        "show_stats": show_stats_value,
        "advice": select_flag(
            options.advice,
            current.advice,
            LintOptionKey.ADVICE,
            provided,
        ),
        "pr_summary_out": (
            resolve_optional_path(project_root, options.pr_summary_out)
            if has_option(LintOptionKey.PR_SUMMARY_OUT)
            else current.pr_summary_out
        ),
        "pr_summary_limit": select_value(
            options.pr_summary_limit,
            current.pr_summary_limit,
            LintOptionKey.PR_SUMMARY_LIMIT,
            provided,
        ),
        "pr_summary_min_severity": (
            normalize_min_severity(options.pr_summary_min_severity)
            if has_option(LintOptionKey.PR_SUMMARY_MIN_SEVERITY)
            else current.pr_summary_min_severity
        ),
        "pr_summary_template": select_value(
            options.pr_summary_template,
            current.pr_summary_template,
            LintOptionKey.PR_SUMMARY_TEMPLATE,
            provided,
        ),
    }
    return overrides


def resolve_tool_filters(
    current_filters: ToolFilters,
    defaults: ToolFilters,
    options: LintOptions,
    has_option: Callable[[LintOptionKey], bool],
) -> ToolFilters:
    """Return merged tool filters combining defaults, config, and CLI values."""

    filters: ToolFilters = {tool: patterns.copy() for tool, patterns in defaults.items()}
    for tool, patterns in current_filters.items():
        filters.setdefault(tool, []).extend(patterns)
    if has_option(LintOptionKey.FILTERS):
        parsed = parse_filters(options.filters)
        for tool, patterns in parsed.items():
            filters.setdefault(tool, []).extend(patterns)
    return {
        tool: list(dict.fromkeys(patterns))
        for tool, patterns in filters.items()
    }


def parse_filters(specs: Iterable[str]) -> ToolFilters:
    """Parse CLI filter specifications into a tool-to-pattern mapping."""

    filters: ToolFilters = {
        tool: list(patterns) for tool, patterns in DEFAULT_TOOL_FILTERS.items()
    }
    for spec in specs:
        if FILTER_SPEC_SEPARATOR not in spec:
            raise ValueError(f"Invalid filter '{spec}'. Expected {FILTER_SPEC_FORMAT}")
        tool, expressions = spec.split(FILTER_SPEC_SEPARATOR, 1)
        tool_key = tool.strip()
        if not tool_key:
            raise ValueError(f"Invalid filter '{spec}'. Tool identifier cannot be empty")
        chunks = [
            chunk.strip()
            for chunk in expressions.split(FILTER_PATTERN_SEPARATOR)
            if chunk.strip()
        ]
        if not chunks:
            continue
        filters.setdefault(tool_key, []).extend(chunks)
    return filters


def normalize_output_mode(value: str) -> OutputMode:
    """Validate and normalise the output mode CLI token."""

    normalized = value.lower()
    if normalized not in _ALLOWED_OUTPUT_MODES:
        raise ValueError(f"invalid output mode '{value}'")
    return cast("OutputMode", normalized)


def normalize_min_severity(value: str) -> SummarySeverity:
    """Validate and normalise the PR summary minimum severity token."""

    normalized = value.lower()
    if normalized not in _ALLOWED_SUMMARY_SEVERITIES:
        raise ValueError(f"invalid summary severity '{value}'")
    return cast("SummarySeverity", normalized)


__all__ = [
    "OutputOverrides",
    "apply_output_overrides",
    "collect_output_overrides",
    "resolve_tool_filters",
    "parse_filters",
    "normalize_output_mode",
    "normalize_min_severity",
]
