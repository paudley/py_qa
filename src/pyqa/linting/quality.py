# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Internal adapters for repository quality enforcement checks."""

from __future__ import annotations

from dataclasses import dataclass
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


@dataclass(slots=True)
class QualityCheckRequest:
    """Describe an invocation of :func:`evaluate_quality_checks`."""

    root: Path
    config: Config
    checks: tuple[str, ...]
    files: tuple[Path, ...] | None = None
    fix: bool = False
    staged: bool = False


@dataclass(slots=True)
class QualitySubsetRequest:
    """Describe parameters required for an internal quality subset run."""

    state: PreparedLintState
    config: Config
    tool_name: str
    checks: tuple[str, ...]
    categories: frozenset[str]
    files: tuple[Path, ...]
    emit_to_logger: bool = False


_ENFORCEMENT_SENSITIVITY: Final[frozenset[str]] = frozenset({"high", "maximum"})


def evaluate_quality_checks(request: QualityCheckRequest) -> QualityCheckResult:
    """Execute quality checks and return the aggregated result.

    Args:
        request: Structured quality check execution parameters.

    Returns:
        QualityCheckResult: Aggregated quality findings produced by the checker.
    """

    checker = QualityChecker(
        root=request.root,
        quality=request.config.quality,
        options=QualityCheckerOptions(
            license_overrides=request.config.license,
            files=request.files,
            checks=request.checks,
            staged=request.staged,
        ),
    )
    return checker.run(fix=request.fix)


def run_license_header_linter(
    state: PreparedLintState,
    *,
    emit_to_logger: bool,
    config: Config,
) -> InternalLintReport:
    """Run the license header enforcement linter."""

    request = QualitySubsetRequest(
        state=state,
        config=config,
        tool_name="license-header",
        checks=("license",),
        categories=frozenset({LICENSE_HEADER_CATEGORY}),
        files=tuple(collect_target_files(state)),
        emit_to_logger=emit_to_logger,
    )
    return _run_quality_subset(request)


def run_copyright_linter(
    state: PreparedLintState,
    *,
    emit_to_logger: bool,
    config: Config,
) -> InternalLintReport:
    """Run the copyright notice consistency linter."""

    request = QualitySubsetRequest(
        state=state,
        config=config,
        tool_name="copyright",
        checks=("license",),
        categories=frozenset({COPYRIGHT_CATEGORY}),
        files=tuple(collect_target_files(state)),
        emit_to_logger=emit_to_logger,
    )
    return _run_quality_subset(request)


def run_python_hygiene_linter(
    state: PreparedLintState,
    *,
    emit_to_logger: bool,
    config: Config,
) -> InternalLintReport:
    """Run the Python hygiene linter covering debug breakpoints and bare excepts."""

    request = QualitySubsetRequest(
        state=state,
        config=config,
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
        files=tuple(collect_python_files(state)),
        emit_to_logger=emit_to_logger,
    )
    return _run_quality_subset(request)


def run_file_size_linter(
    state: PreparedLintState,
    *,
    emit_to_logger: bool,
    config: Config,
) -> InternalLintReport:
    """Run the file size threshold linter."""

    request = QualitySubsetRequest(
        state=state,
        config=config,
        tool_name="file-size",
        checks=("file-size",),
        categories=frozenset({"file-size"}),
        files=tuple(collect_target_files(state)),
        emit_to_logger=emit_to_logger,
    )
    return _run_quality_subset(request)


def run_pyqa_schema_sync_linter(
    state: PreparedLintState,
    *,
    emit_to_logger: bool,
    config: Config,
) -> InternalLintReport:
    """Run the pyqa schema synchronisation linter."""

    request = QualitySubsetRequest(
        state=state,
        config=config,
        tool_name="pyqa-schema-sync",
        checks=("schema",),
        categories=frozenset({SCHEMA_SYNC_CATEGORY}),
        files=tuple(collect_target_files(state)),
        emit_to_logger=emit_to_logger,
    )
    return _run_quality_subset(request)


def run_pyqa_python_hygiene_linter(
    state: PreparedLintState,
    *,
    emit_to_logger: bool,
    config: Config,
) -> InternalLintReport:
    """Run the pyqa-specific Python hygiene checks."""

    request = QualitySubsetRequest(
        state=state,
        config=config,
        tool_name="pyqa-python-hygiene",
        checks=("python",),
        categories=frozenset({PYTHON_HYGIENE_SYSTEM_EXIT, PYTHON_HYGIENE_PRINT}),
        files=tuple(collect_python_files(state)),
        emit_to_logger=emit_to_logger,
    )
    return _run_quality_subset(request)


def _run_quality_subset(request: QualitySubsetRequest) -> InternalLintReport:
    """Execute a specific quality check and convert results into diagnostics."""

    state = request.state
    config = request.config
    files = request.files
    tool_name = request.tool_name
    categories = request.categories
    checks = request.checks

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

    quality_request = QualityCheckRequest(
        root=state.root,
        config=config,
        checks=checks,
        files=tuple(files),
        fix=False,
    )
    result = evaluate_quality_checks(quality_request)

    diagnostics: list[Diagnostic] = []
    stdout_lines: list[str] = []
    for issue in result.issues:
        if categories and issue.check not in categories:
            continue
        diagnostic = _issue_to_diagnostic(issue, tool_name=tool_name, root=state.root)
        if diagnostic is None:
            continue
        if _diagnostic_suppressed(state, diagnostic):
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


def _diagnostic_suppressed(state: PreparedLintState, diagnostic: Diagnostic) -> bool:
    suppressions = getattr(state, "suppressions", None)
    if suppressions is None or not diagnostic.file or diagnostic.line is None:
        return False
    diagnostic_path = Path(diagnostic.file)
    if not diagnostic_path.is_absolute():
        diagnostic_path = (state.root / diagnostic_path).resolve()
    return bool(
        suppressions.should_suppress(
            diagnostic_path,
            diagnostic.line,
            tool=diagnostic.tool,
            code=diagnostic.code or diagnostic.tool,
        )
    )


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
