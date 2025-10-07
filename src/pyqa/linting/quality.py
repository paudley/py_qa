# SPDX-License-Identifier: MIT
"""Internal quality checker orchestrated as an internal tool."""

from __future__ import annotations

from pathlib import Path

from pyqa.cli.commands.lint.preparation import PreparedLintState
from pyqa.compliance.quality import (
    QualityChecker,
    QualityCheckerOptions,
    QualityIssue,
    QualityIssueLevel,
)
from pyqa.config import Config
from pyqa.core.models import Diagnostic, ToolExitCategory, ToolOutcome
from pyqa.core.severity import Severity
from pyqa.filesystem.paths import normalize_path_key

from .base import InternalLintReport
from .utils import collect_python_files

_QUALITY_SENSITIVITY_THRESHOLD: set[str] = {"high", "maximum"}


def run_quality_linter(
    state: PreparedLintState,
    *,
    emit_to_logger: bool,
    config: Config,
) -> InternalLintReport:
    """Execute the internal quality checker using CLI state and config."""

    del emit_to_logger  # Output is handled via ToolOutcome payloads.

    files = collect_python_files(state)
    if not files:
        outcome = ToolOutcome(
            tool="quality",
            action="check",
            returncode=0,
            stdout=["No files eligible for quality checks"],
            stderr=[],
            diagnostics=[],
            exit_category=ToolExitCategory.SUCCESS,
        )
        return InternalLintReport(outcome=outcome, files=tuple(files))

    should_enforce = config.quality.enforce_in_lint or config.severity.sensitivity in _QUALITY_SENSITIVITY_THRESHOLD
    if not should_enforce:
        outcome = ToolOutcome(
            tool="quality",
            action="check",
            returncode=0,
            stdout=["Quality checks skipped (enforcement disabled)"],
            stderr=[],
            diagnostics=[],
            exit_category=ToolExitCategory.SUCCESS,
        )
        return InternalLintReport(outcome=outcome, files=tuple(files))

    checker = QualityChecker(
        root=state.root,
        quality=config.quality,
        options=QualityCheckerOptions(
            license_overrides=config.license,
            files=tuple(files),
            checks={"license"},
        ),
    )
    quality_result = checker.run(fix=False)
    diagnostics: list[Diagnostic] = []
    stdout_lines: list[str] = []
    for issue in quality_result.issues:
        diagnostic = _quality_issue_to_diagnostic(issue, root=state.root)
        if diagnostic is None:
            continue
        diagnostics.append(diagnostic)
        location = diagnostic.file or ""
        if not location and issue.path is not None:
            location = normalize_path_key(issue.path, base_dir=state.root)
        stdout_lines.append(_format_quality_issue_output(diagnostic, location))

    returncode = 1 if any(diag.severity is Severity.ERROR for diag in diagnostics) else 0
    exit_category = ToolExitCategory.DIAGNOSTIC if returncode != 0 else ToolExitCategory.SUCCESS
    outcome = ToolOutcome(
        tool="quality",
        action="check",
        returncode=returncode,
        stdout=stdout_lines,
        stderr=[],
        diagnostics=diagnostics,
        exit_category=exit_category,
    )
    return InternalLintReport(outcome=outcome, files=tuple(files))


def _quality_issue_to_diagnostic(issue: QualityIssue, *, root: Path) -> Diagnostic | None:
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
    if location:
        return f"[{diagnostic.severity.value}] {location}: {diagnostic.message}"
    return f"[{diagnostic.severity.value}] {diagnostic.message}"


_QUALITY_SEVERITY_MAP: dict[QualityIssueLevel, Severity] = {
    QualityIssueLevel.ERROR: Severity.ERROR,
    QualityIssueLevel.WARNING: Severity.WARNING,
}


__all__ = [
    "run_quality_linter",
]
