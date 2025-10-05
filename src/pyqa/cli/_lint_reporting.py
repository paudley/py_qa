# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Reporting helpers for the lint CLI."""

from __future__ import annotations

from pathlib import Path

from ..config import Config, SensitivityLevel
from ..filesystem.paths import normalize_path_key
from ..models import Diagnostic, RunResult, ToolOutcome
from ..quality import QualityChecker, QualityCheckerOptions, QualityIssue, QualityIssueLevel
from ..reporting.emitters import write_json_report, write_pr_summary, write_sarif_report
from ..reporting.formatters import render
from ..severity import Severity
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


_QUALITY_SENSITIVITY_THRESHOLD: set[str] = {
    SensitivityLevel.HIGH.value,
    SensitivityLevel.MAXIMUM.value,
}


def append_internal_quality_checks(
    *,
    config: Config,
    root: Path,
    run_result: RunResult,
    logger: CLILogger | None = None,
) -> None:
    """Run additional quality checks and append results when sensitivity is maximum."""
    if not config.quality.enforce_in_lint and config.severity.sensitivity not in _QUALITY_SENSITIVITY_THRESHOLD:
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

    diagnostics: list[Diagnostic] = []
    stdout_lines: list[str] = []
    for issue in quality_result.issues:
        diagnostic = _quality_issue_to_diagnostic(issue, root=root)
        if diagnostic is None:
            continue
        diagnostics.append(diagnostic)
        location = diagnostic.file
        if not location and issue.path is not None:
            location = normalize_path_key(issue.path, base_dir=root)
        stdout_lines.append(_format_quality_issue_output(diagnostic, location))
    if not diagnostics:
        return

    has_error = any(diag.severity is Severity.ERROR for diag in diagnostics)
    diagnostic_outcome = ToolOutcome(
        tool="quality",
        action="license",
        returncode=1 if has_error else 0,
        stdout=stdout_lines,
        stderr=[],
        diagnostics=diagnostics,
    )
    run_result.outcomes.append(diagnostic_outcome)
    if has_error:
        run_result.outcomes.append(
            ToolOutcome(
                tool="quality",
                action="enforce",
                returncode=1,
                stdout=[],
                stderr=[],
                diagnostics=[],
            ),
        )
    if logger:
        count = len(diagnostics)
        plural = "issue" if count == 1 else "issues"
        logger.warn(
            f"Appended {count} license {plural} from quality checks due to heightened sensitivity",
        )


def _quality_issue_to_diagnostic(issue: QualityIssue, *, root: Path) -> Diagnostic | None:
    """Convert a quality issue to a lint diagnostic."""
    severity = _QUALITY_SEVERITY_MAP.get(issue.level)
    if severity is None:
        return None

    file_path = None
    if issue.path is not None:
        file_path = normalize_path_key(issue.path, base_dir=root)

    return Diagnostic(
        file=file_path,
        line=None,
        column=None,
        severity=severity,
        message=issue.message,
        tool="quality",
        code=f"quality:{issue.level.value}",
    )


def _format_quality_issue_output(diagnostic: Diagnostic, location: str | None) -> str:
    """Return a human-readable summary for quality issue stdout."""

    if location:
        return f"[{diagnostic.severity.value}] {location}: {diagnostic.message}"
    return f"[{diagnostic.severity.value}] {diagnostic.message}"


_QUALITY_SEVERITY_MAP: dict[QualityIssueLevel, Severity] = {
    QualityIssueLevel.ERROR: Severity.ERROR,
    QualityIssueLevel.WARNING: Severity.WARNING,
}


__all__ = ["handle_reporting", "append_internal_quality_checks"]
