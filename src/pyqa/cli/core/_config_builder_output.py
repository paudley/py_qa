# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Helpers for constructing output configuration overrides."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path
from typing import TypedDict, cast

from ...config import OutputConfig
from ._config_builder_constants import (
    _ALLOWED_OUTPUT_MODES,
    _ALLOWED_SUMMARY_SEVERITIES,
    DEFAULT_TOOL_FILTERS,
    FILTER_PATTERN_SEPARATOR,
    FILTER_SPEC_FORMAT,
    FILTER_SPEC_SEPARATOR,
    LintOptionKey,
    OutputMode,
    SummarySeverity,
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
    """Return ``current`` updated with the supplied override mapping.

    Args:
        current: Baseline output configuration prior to mutation.
        overrides: Override values derived from CLI selections.

    Returns:
        OutputConfig: New output configuration reflecting ``overrides``.
    """

    return current.model_copy(update=dict(overrides), deep=True)


def collect_output_overrides(
    current: OutputConfig,
    options: LintOptions,
    project_root: Path,
    has_option: Callable[[LintOptionKey], bool],
) -> OutputOverrides:
    """Return the output overrides derived from CLI inputs.

    Args:
        current: Existing output configuration prior to applying overrides.
        options: Composed CLI options bundle derived from user arguments.
        project_root: Resolved project root used for relative path decisions.
        has_option: Predicate indicating whether a CLI flag was provided.

    Returns:
        OutputOverrides: Mapping of normalized output overrides including
        toggles, filters, and PR summary adjustments.
    """

    provided = options.provided
    output_bundle = options.output_bundle
    display = output_bundle.display
    summary = output_bundle.summary

    tool_filters = resolve_tool_filters(
        current.tool_filters,
        DEFAULT_TOOL_FILTERS,
        options,
        has_option,
    )

    quiet_value = select_flag(display.quiet, current.quiet, LintOptionKey.QUIET, provided)
    show_passing_value = select_flag(
        summary.show_passing,
        current.show_passing,
        LintOptionKey.SHOW_PASSING,
        provided,
    )
    show_stats_value = select_flag(
        not summary.no_stats,
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
            display.verbose,
            current.verbose,
            LintOptionKey.VERBOSE,
            provided,
        ),
        "quiet": quiet_value,
        "color": select_flag(
            not display.no_color,
            current.color,
            LintOptionKey.NO_COLOR,
            provided,
        ),
        "emoji": select_flag(
            not display.no_emoji,
            current.emoji,
            LintOptionKey.NO_EMOJI,
            provided,
        ),
        "output": (
            normalize_output_mode(display.output_mode) if has_option(LintOptionKey.OUTPUT_MODE) else current.output
        ),
        "show_passing": show_passing_value,
        "show_stats": show_stats_value,
        "advice": select_flag(
            display.advice,
            current.advice,
            LintOptionKey.ADVICE,
            provided,
        ),
        "pr_summary_out": (
            resolve_optional_path(project_root, summary.pr_summary_out)
            if has_option(LintOptionKey.PR_SUMMARY_OUT)
            else current.pr_summary_out
        ),
        "pr_summary_limit": select_value(
            summary.pr_summary_limit,
            current.pr_summary_limit,
            LintOptionKey.PR_SUMMARY_LIMIT,
            provided,
        ),
        "pr_summary_min_severity": (
            normalize_min_severity(summary.pr_summary_min_severity)
            if has_option(LintOptionKey.PR_SUMMARY_MIN_SEVERITY)
            else current.pr_summary_min_severity
        ),
        "pr_summary_template": select_value(
            summary.pr_summary_template,
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
    """Return merged tool filters combining defaults, config, and CLI values.

    Args:
        current_filters: Filters from the persisted configuration file.
        defaults: Built-in default filters shared across commands.
        options: Composed CLI options bundle derived from user arguments.
        has_option: Predicate indicating whether a CLI flag was provided.

    Returns:
        ToolFilters: Deduplicated mapping of tool names to suppression
        patterns derived from defaults, config, and CLI input.
    """

    filters: ToolFilters = {tool: patterns.copy() for tool, patterns in defaults.items()}
    for tool, patterns in current_filters.items():
        filters.setdefault(tool, []).extend(patterns)
    if has_option(LintOptionKey.FILTERS):
        parsed = parse_filters(options.selection_options.filters)
        for tool, patterns in parsed.items():
            filters.setdefault(tool, []).extend(patterns)
    return {tool: list(dict.fromkeys(patterns)) for tool, patterns in filters.items()}


def parse_filters(specs: Iterable[str]) -> ToolFilters:
    """Parse CLI filter specifications into a tool-to-pattern mapping.

    Args:
        specs: Iterable of CLI filter specifications in ``TOOL:pattern`` format.

    Returns:
        ToolFilters: Mapping of tool identifiers to associated filter patterns.

    Raises:
        ValueError: If a specification omits the tool identifier or separator.
    """

    filters: ToolFilters = {tool: list(patterns) for tool, patterns in DEFAULT_TOOL_FILTERS.items()}
    for spec in specs:
        if FILTER_SPEC_SEPARATOR not in spec:
            raise ValueError(f"Invalid filter '{spec}'. Expected {FILTER_SPEC_FORMAT}")
        tool, expressions = spec.split(FILTER_SPEC_SEPARATOR, 1)
        tool_key = tool.strip()
        if not tool_key:
            raise ValueError(f"Invalid filter '{spec}'. Tool identifier cannot be empty")
        chunks = [chunk.strip() for chunk in expressions.split(FILTER_PATTERN_SEPARATOR) if chunk.strip()]
        if not chunks:
            continue
        filters.setdefault(tool_key, []).extend(chunks)
    return filters


def normalize_output_mode(value: str) -> OutputMode:
    """Validate and normalise the output mode CLI token.

    Args:
        value: CLI token supplied for output mode selection.

    Returns:
        OutputMode: Normalised output mode literal.

    Raises:
        ValueError: If the provided token is not recognised.
    """

    normalized = value.lower()
    if normalized not in _ALLOWED_OUTPUT_MODES:
        raise ValueError(f"invalid output mode '{value}'")
    return cast("OutputMode", normalized)


def normalize_min_severity(value: str) -> SummarySeverity:
    """Validate and normalise the PR summary minimum severity token.

    Args:
        value: CLI token supplied for minimum severity selection.

    Returns:
        SummarySeverity: Normalised minimum severity literal.

    Raises:
        ValueError: If the provided token is not recognised.
    """

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
