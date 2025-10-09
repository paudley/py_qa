# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Internal adapters for repository quality enforcement checks."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Final

from pyqa.cli.commands.lint.preparation import PreparedLintState
from pyqa.compliance.quality import (
    COPYRIGHT_CATEGORY,
    LICENSE_HEADER_CATEGORY,
    PYTHON_HYGIENE_BARE_EXCEPT,
    PYTHON_HYGIENE_BREAKPOINT,
    PYTHON_HYGIENE_BROAD_EXCEPTION,
    PYTHON_HYGIENE_CATEGORY,
    PYTHON_HYGIENE_DEBUG_IMPORT,
    PYTHON_HYGIENE_MAIN_GUARD,
    PYTHON_HYGIENE_PRINT,
    PYTHON_HYGIENE_SYSTEM_EXIT,
    SCHEMA_SYNC_CATEGORY,
    QualityChecker,
    QualityCheckerOptions,
    QualityCheckResult,
    QualityIssue,
    QualityIssueLevel,
)
from pyqa.config import Config
from pyqa.core.models import Diagnostic, ToolExitCategory, ToolOutcome
from pyqa.core.severity import Severity
from pyqa.filesystem.paths import normalize_path_key

from .base import InternalLintReport
from .utils import collect_python_files, collect_target_files

_ENFORCEMENT_SENSITIVITY: Final[frozenset[str]] = frozenset({"high", "maximum"})


def evaluate_quality_checks(
    *,
    root: Path,
    config: Config,
    checks: Iterable[str],
    files: Sequence[Path] | None,
    fix: bool = False,
    staged: bool = False,
) -> QualityCheckResult:
    """Execute quality checks and return the aggregated result.

    Args:
        root: Repository root used to seed the quality checker.
        config: Loaded configuration containing quality and license settings.
        checks: Collection of quality check identifiers to execute.
        files: Optional list of explicit files to analyse.
        fix: Whether fix-capable checks should attempt automatic remediation.

    Returns:
        QualityCheckResult: Aggregated quality findings produced by the checker.
    """

    checker = QualityChecker(
        root=root,
        quality=config.quality,
        options=QualityCheckerOptions(
            license_overrides=config.license,
            files=tuple(files) if files else None,
            checks=tuple(checks),
            staged=staged,
        ),
    )
    return checker.run(fix=fix)


def run_license_header_linter(
    state: PreparedLintState,
    *,
    emit_to_logger: bool,
    config: Config,
) -> InternalLintReport:
    """Run the license header enforcement linter."""

    return _run_quality_subset(
        state,
        config,
        emit_to_logger=emit_to_logger,
        tool_name="license-header",
        checks=("license",),
        categories=frozenset({LICENSE_HEADER_CATEGORY}),
        files=collect_target_files(state),
    )


def run_copyright_linter(
    state: PreparedLintState,
    *,
    emit_to_logger: bool,
    config: Config,
) -> InternalLintReport:
    """Run the copyright notice consistency linter."""

    return _run_quality_subset(
        state,
        config,
        emit_to_logger=emit_to_logger,
        tool_name="copyright",
        checks=("license",),
        categories=frozenset({COPYRIGHT_CATEGORY}),
        files=collect_target_files(state),
    )


def run_python_hygiene_linter(
    state: PreparedLintState,
    *,
    emit_to_logger: bool,
    config: Config,
) -> InternalLintReport:
    """Run the Python hygiene linter covering debug breakpoints and bare excepts."""

    return _run_quality_subset(
        state,
        config,
        emit_to_logger=emit_to_logger,
        tool_name="python-hygiene",
        checks=("python",),
        categories=frozenset(
            {
                PYTHON_HYGIENE_CATEGORY,
                PYTHON_HYGIENE_BREAKPOINT,
                PYTHON_HYGIENE_BARE_EXCEPT,
                PYTHON_HYGIENE_MAIN_GUARD,
                PYTHON_HYGIENE_BROAD_EXCEPTION,
                PYTHON_HYGIENE_DEBUG_IMPORT,
            }
        ),
        files=collect_python_files(state),
    )


def run_file_size_linter(
    state: PreparedLintState,
    *,
    emit_to_logger: bool,
    config: Config,
) -> InternalLintReport:
    """Run the file size threshold linter."""

    return _run_quality_subset(
        state,
        config,
        emit_to_logger=emit_to_logger,
        tool_name="file-size",
        checks=("file-size",),
        categories=frozenset({"file-size"}),
        files=collect_target_files(state),
    )


def run_pyqa_schema_sync_linter(
    state: PreparedLintState,
    *,
    emit_to_logger: bool,
    config: Config,
) -> InternalLintReport:
    """Run the pyqa schema synchronisation linter."""

    return _run_quality_subset(
        state,
        config,
        emit_to_logger=emit_to_logger,
        tool_name="pyqa-schema-sync",
        checks=("schema",),
        categories=frozenset({SCHEMA_SYNC_CATEGORY}),
        files=collect_target_files(state),
    )


def run_pyqa_python_hygiene_linter(
    state: PreparedLintState,
    *,
    emit_to_logger: bool,
    config: Config,
) -> InternalLintReport:
    """Run the pyqa-specific Python hygiene checks."""

    return _run_quality_subset(
        state,
        config,
        emit_to_logger=emit_to_logger,
        tool_name="pyqa-python-hygiene",
        checks=("python",),
        categories=frozenset({PYTHON_HYGIENE_SYSTEM_EXIT, PYTHON_HYGIENE_PRINT}),
        files=collect_python_files(state),
    )


def _run_quality_subset(
    state: PreparedLintState,
    config: Config,
    *,
    emit_to_logger: bool,
    tool_name: str,
    checks: Iterable[str],
    categories: frozenset[str],
    files: Sequence[Path],
) -> InternalLintReport:
    """Execute a specific quality check and convert results into diagnostics."""

    del emit_to_logger

    if not files:
        outcome = ToolOutcome(
            tool=tool_name,
            action="check",
            returncode=0,
            stdout=["No files matched quality selection"],
            stderr=[],
            diagnostics=[],
            exit_category=ToolExitCategory.SUCCESS,
        )
        return InternalLintReport(outcome=outcome, files=tuple(files))

    raw_sensitivity = config.severity.sensitivity
    sensitivity = str(getattr(raw_sensitivity, "value", raw_sensitivity)).lower() if raw_sensitivity is not None else ""
    should_enforce = config.quality.enforce_in_lint or sensitivity in _ENFORCEMENT_SENSITIVITY
    if not should_enforce:
        outcome = ToolOutcome(
            tool=tool_name,
            action="check",
            returncode=0,
            stdout=["Quality enforcement disabled for current sensitivity"],
            stderr=[],
            diagnostics=[],
            exit_category=ToolExitCategory.SUCCESS,
        )
        return InternalLintReport(outcome=outcome, files=tuple(files))

    result = evaluate_quality_checks(
        root=state.root,
        config=config,
        checks=checks,
        files=files,
        fix=False,
    )

    diagnostics: list[Diagnostic] = []
    stdout_lines: list[str] = []
    for issue in result.issues:
        if categories and issue.check not in categories:
            continue
        diagnostic = _issue_to_diagnostic(issue, tool_name=tool_name, root=state.root)
        if diagnostic is None:
            continue
        diagnostics.append(diagnostic)
        location = diagnostic.file or ""
        if not location and issue.path is not None:
            location = normalize_path_key(issue.path, base_dir=state.root)
        stdout_lines.append(_format_issue_output(diagnostic, location))

    returncode = 1 if any(diag.severity is Severity.ERROR for diag in diagnostics) else 0
    exit_category = ToolExitCategory.DIAGNOSTIC if returncode else ToolExitCategory.SUCCESS
    outcome = ToolOutcome(
        tool=tool_name,
        action="check",
        returncode=returncode,
        stdout=stdout_lines,
        stderr=[],
        diagnostics=diagnostics,
        exit_category=exit_category,
    )
    return InternalLintReport(outcome=outcome, files=tuple(files))


def _issue_to_diagnostic(issue: QualityIssue, *, tool_name: str, root: Path) -> Diagnostic | None:
    """Translate a :class:`QualityIssue` into a diagnostic structure."""

    severity = _SEVERITY_MAP.get(issue.level)
    if severity is None:
        return None

    file_path = None
    if issue.path is not None:
        file_path = normalize_path_key(issue.path, base_dir=root)

    code_suffix = issue.check or issue.level.value
    return Diagnostic(
        file=file_path,
        line=None,
        column=None,
        severity=severity,
        message=issue.message,
        tool=tool_name,
        code=f"{tool_name}:{code_suffix}",
    )


def _format_issue_output(diagnostic: Diagnostic, location: str | None) -> str:
    """Return a concise human-readable summary for stdout."""

    if location:
        return f"[{diagnostic.severity.value}] {location}: {diagnostic.message}"
    return f"[{diagnostic.severity.value}] {diagnostic.message}"


_SEVERITY_MAP: Final[dict[QualityIssueLevel, Severity]] = {
    QualityIssueLevel.ERROR: Severity.ERROR,
    QualityIssueLevel.WARNING: Severity.WARNING,
}


__all__ = [
    "evaluate_quality_checks",
    "run_license_header_linter",
    "run_copyright_linter",
    "run_python_hygiene_linter",
    "run_file_size_linter",
    "run_pyqa_schema_sync_linter",
    "run_pyqa_python_hygiene_linter",
]
