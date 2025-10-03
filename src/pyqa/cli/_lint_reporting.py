# SPDX-License-Identifier: MIT
"""Reporting helpers for the lint CLI."""

from __future__ import annotations

from pathlib import Path

from ..config import Config, SensitivityLevel
from ..models import RunResult, ToolOutcome
from ..quality import QualityChecker, QualityCheckerOptions
from ..reporting.emitters import write_json_report, write_pr_summary, write_sarif_report
from ..reporting.formatters import render
from ._lint_cli_models import LintOutputArtifacts
from .shared import CLILogger


def handle_reporting(
    result: RunResult,
    config: Config,
    artifacts: LintOutputArtifacts,
    *,
    logger: CLILogger | None = None,
) -> None:
    """Render console output and emit optional artifacts for ``pyqa lint``."""

    render(result, config.output)
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


def append_internal_quality_checks(
    *,
    config: Config,
    root: Path,
    run_result: RunResult,
    logger: CLILogger | None = None,
) -> None:
    """Run additional quality checks and append results when sensitivity is maximum."""

    if config.severity.sensitivity != SensitivityLevel.MAXIMUM.value:
        return
    if not run_result.files:
        return

    checker = QualityChecker(
        root=root,
        quality=config.quality,
        options=QualityCheckerOptions(
            license_overrides=config.license,
            files=run_result.files,
            checks={"license"},
        ),
    )
    quality_result = checker.run(fix=False)
    if not quality_result.issues:
        return

    added_outcomes = []
    for issue in quality_result.issues:
        added_outcomes.append(
            ToolOutcome(
                tool="quality",
                action="license",
                returncode=0,
                stdout=[issue.message],
                stderr=[],
                diagnostics=[],
            ),
        )
    run_result.outcomes.extend(added_outcomes)
    if logger:
        count = len(added_outcomes)
        plural = "issue" if count == 1 else "issues"
        logger.warn(
            f"Appended {count} license {plural} from quality checks due to maximum sensitivity",
        )


__all__ = ["handle_reporting", "append_internal_quality_checks"]
