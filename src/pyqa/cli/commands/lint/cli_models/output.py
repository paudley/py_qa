# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Output and reporting dependency factories for the lint CLI."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from ....core.shared import Depends
from ..params import LintOutputParams, LintReportingParams, LintSummaryParams
from .coercion import _coerce_output_mode, _coerce_pr_summary_severity
from .constants import (
    ADVICE_HELP,
    OUTPUT_MODE_CONCISE,
    OUTPUT_MODE_HELP,
    PR_SUMMARY_MIN_SEVERITY_HELP,
    PR_SUMMARY_OUT_HELP,
    PR_SUMMARY_TEMPLATE_HELP,
    REPORT_JSON_HELP,
    SARIF_HELP,
)
from .models import LintOutputToggles


def _output_toggle_dependency(
    verbose: Annotated[bool, typer.Option(False, help="Verbose output.")],
    quiet: Annotated[bool, typer.Option(False, "--quiet", "-q", help="Minimal output.")],
    no_color: Annotated[bool, typer.Option(False, help="Disable ANSI colour output.")],
    no_emoji: Annotated[bool, typer.Option(False, help="Disable emoji output.")],
    debug: Annotated[bool, typer.Option(False, "--debug", help="Emit detailed execution diagnostics.")],
) -> LintOutputToggles:
    """Return the raw CLI toggles backing output behaviour.

    Args:
        verbose: Flag enabling verbose console output.
        quiet: Flag suppressing non-essential console output.
        no_color: Flag disabling ANSI colour rendering.
        no_emoji: Flag disabling emoji rendering.
        debug: Flag enabling detailed execution diagnostics.

    Returns:
        LintOutputToggles: Structured toggle state derived from CLI flags.
    """

    return LintOutputToggles(
        verbose=verbose,
        quiet=quiet,
        no_color=no_color,
        no_emoji=no_emoji,
        debug=debug,
    )


def _output_params_dependency(
    toggles: Annotated[LintOutputToggles, Depends(_output_toggle_dependency)],
    output_mode: Annotated[str, typer.Option(OUTPUT_MODE_CONCISE, "--output", help=OUTPUT_MODE_HELP)],
) -> LintOutputParams:
    """Return rendering parameters for console output.

    Args:
        toggles: Structured booleans describing output toggles.
        output_mode: Raw output mode supplied by the user.

    Returns:
        LintOutputParams: Structured rendering parameters.
    """

    return LintOutputParams(
        verbose=toggles.verbose,
        quiet=toggles.quiet,
        no_color=toggles.no_color,
        no_emoji=toggles.no_emoji,
        debug=toggles.debug,
        output_mode=_coerce_output_mode(output_mode),
    )


def _reporting_params_dependency(
    show_passing: Annotated[bool, typer.Option(False, help="Include successful diagnostics in output.")],
    no_stats: Annotated[bool, typer.Option(False, help="Suppress summary statistics.")],
    report_json: Annotated[Path | None, typer.Option(None, help=REPORT_JSON_HELP)],
    sarif_out: Annotated[Path | None, typer.Option(None, help=SARIF_HELP)],
    pr_summary_out: Annotated[Path | None, typer.Option(None, help=PR_SUMMARY_OUT_HELP)],
) -> LintReportingParams:
    """Return reporting parameters determining diagnostic artifact output.

    Args:
        show_passing: Whether to include passing diagnostics in output.
        no_stats: Whether to suppress summary statistics.
        report_json: Optional JSON report destination.
        sarif_out: Optional SARIF output path.
        pr_summary_out: Optional PR summary output path.

    Returns:
        LintReportingParams: Structured reporting options.
    """

    return LintReportingParams(
        show_passing=show_passing,
        no_stats=no_stats,
        report_json=report_json,
        sarif_out=sarif_out,
        pr_summary_out=pr_summary_out,
    )


def _summary_params_dependency(
    pr_summary_limit: Annotated[
        int, typer.Option(100, "--pr-summary-limit", help="Maximum diagnostics in PR summary.")
    ],
    pr_summary_min_severity: Annotated[
        str,
        typer.Option("warning", "--pr-summary-min-severity", help=PR_SUMMARY_MIN_SEVERITY_HELP),
    ],
    pr_summary_template: Annotated[
        str,
        typer.Option(
            "- **{severity}** `{tool}` {message} ({location})",
            "--pr-summary-template",
            help=PR_SUMMARY_TEMPLATE_HELP,
        ),
    ],
    advice: Annotated[bool, typer.Option(False, "--advice", help=ADVICE_HELP)],
) -> LintSummaryParams:
    """Return PR summary configuration derived from CLI flags.

    Args:
        pr_summary_limit: Maximum number of diagnostics in the summary.
        pr_summary_min_severity: Minimum severity to include in the summary.
        pr_summary_template: Template string used to format entries.
        advice: Whether SOLID advice should be included.

    Returns:
        LintSummaryParams: Structured summary configuration for lint.
    """

    return LintSummaryParams(
        pr_summary_limit=pr_summary_limit,
        pr_summary_min_severity=_coerce_pr_summary_severity(pr_summary_min_severity),
        pr_summary_template=pr_summary_template,
        advice=advice,
    )


__all__ = [
    "_output_params_dependency",
    "_output_toggle_dependency",
    "_reporting_params_dependency",
    "_summary_params_dependency",
]
