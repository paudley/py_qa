# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Reporting helpers for the lint CLI."""

from __future__ import annotations

from pyqa.core.models import RunResult

from ....analysis.providers import NullAnnotationProvider
from ....config import Config
from ....interfaces.analysis import AnnotationProvider
from ....reporting import render, write_json_report, write_pr_summary, write_sarif_report
from ....reporting.output.highlighting import set_annotation_provider as set_highlighting_annotation_provider
from ....reporting.presenters.emitters import set_annotation_provider as set_emitter_annotation_provider
from ...core.shared import CLILogger
from .params import LintOutputArtifacts


def handle_reporting(
    result: RunResult,
    config: Config,
    artifacts: LintOutputArtifacts,
    *,
    logger: CLILogger | None = None,
    annotation_provider: AnnotationProvider | None = None,
) -> None:
    """Render console output and emit optional artifacts for ``pyqa lint``."""

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
        write_pr_summary(
            result,
            artifacts.pr_summary_out,
            limit=config.output.pr_summary_limit,
            min_severity=config.output.pr_summary_min_severity,
            template=config.output.pr_summary_template,
        )
        if logger:
            logger.ok(f"Saved PR summary to {artifacts.pr_summary_out}")


__all__ = ["handle_reporting"]
