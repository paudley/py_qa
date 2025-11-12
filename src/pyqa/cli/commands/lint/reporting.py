# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Reporting helpers for the lint CLI."""

from __future__ import annotations

from pyqa.core.models import RunResult
from pyqa.interfaces.config import Config as ConfigProtocol
from pyqa.interfaces.linting import CLILogger as CLILoggerView
from pyqa.interfaces.linting import LintOutputArtifacts

from ....analysis.providers import NullAnnotationProvider
from ....interfaces.analysis import AnnotationProvider
from ....reporting import render
from ....reporting.output.highlighting import set_annotation_provider as set_highlighting_annotation_provider
from ....reporting.presenters.emitters import (
    PRSummaryOptions,
)
from ....reporting.presenters.emitters import set_annotation_provider as set_emitter_annotation_provider
from ....reporting.presenters.emitters import (
    write_json_report,
    write_pr_summary,
    write_sarif_report,
)


def handle_reporting(
    result: RunResult,
    config: ConfigProtocol,
    artifacts: LintOutputArtifacts,
    *,
    logger: CLILoggerView | None = None,
    annotation_provider: AnnotationProvider | None = None,
) -> None:
    """Render console output and emit optional artifacts for ``pyqa lint``.

    Args:
        result: Aggregated lint run result containing diagnostics to render.
        config: Runtime configuration describing output preferences.
        artifacts: Filesystem destinations for optional report artifacts.
        logger: Optional CLI logger used to report emitted artifact paths.
        annotation_provider: Optional annotation provider used to augment reporting.

    This function renders console output and may write reporting artifacts.
    """

    provider = annotation_provider or NullAnnotationProvider()
    set_highlighting_annotation_provider(provider)
    set_emitter_annotation_provider(provider)
    render(result, config.output, annotation_provider=provider)
    if artifacts.report_json:
        write_json_report(result, artifacts.report_json)
        if logger:
            logger.ok(f"Saved JSON report to {artifacts.report_json}")
    if artifacts.sarif_out:
        write_sarif_report(result, artifacts.sarif_out)
        if logger:
            logger.ok(f"Saved SARIF report to {artifacts.sarif_out}")
    if artifacts.pr_summary_out:
        pr_options = PRSummaryOptions(
            limit=config.output.pr_summary_limit,
            min_severity=config.output.pr_summary_min_severity,
            template=config.output.pr_summary_template,
        )
        write_pr_summary(result, artifacts.pr_summary_out, options=pr_options)
        if logger:
            logger.ok(f"Saved PR summary to {artifacts.pr_summary_out}")


__all__ = ["handle_reporting"]
