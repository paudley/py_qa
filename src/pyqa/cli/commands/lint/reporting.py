# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Reporting helpers for the lint CLI."""

from __future__ import annotations

from pathlib import Path

from pyqa.core.models import Diagnostic, RunResult, ToolOutcome
from pyqa.core.severity import Severity

from ....analysis.services import resolve_annotation_provider
from ....compliance.quality import (
    QualityChecker,
    QualityCheckerOptions,
    QualityIssue,
    QualityIssueLevel,
)
from ....config import Config, SensitivityLevel
from ....filesystem.paths import normalize_path_key
from ....interfaces.analysis import AnnotationProvider
from ....linting.base import InternalLintReport
from ....linting.registry import InternalLinterDefinition, iter_internal_linters
from ....reporting import render, write_json_report, write_pr_summary, write_sarif_report
from ....reporting.output.highlighting import set_annotation_provider as set_highlighting_annotation_provider
from ....reporting.presenters.emitters import set_annotation_provider as set_emitter_annotation_provider
from ...core.shared import CLILogger
from .params import LintOutputArtifacts
from .preparation import PreparedLintState


def handle_reporting(
    result: RunResult,
    config: Config,
    artifacts: LintOutputArtifacts,
    *,
    logger: CLILogger | None = None,
    annotation_provider: AnnotationProvider | None = None,
) -> None:
    """Render console output and emit optional artifacts for ``pyqa lint``.

    Args:
        result: Aggregated run result produced by the orchestrator.
        config: Effective configuration controlling output modes.
        artifacts: Requested artifact destinations for lint output.
        logger: Optional CLI logger used to report artifact creation.
        annotation_provider: Annotation provider used for highlighting and advice.
    """
    provider = annotation_provider or resolve_annotation_provider()
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


_QUALITY_SENSITIVITY_THRESHOLD: set[str] = {
    SensitivityLevel.HIGH.value,
    SensitivityLevel.MAXIMUM.value,
}


def append_internal_quality_checks(
    *,
    config: Config,
    state: PreparedLintState,
    run_result: RunResult,
    logger: CLILogger | None = None,
) -> None:
    """Run internal quality and docstring checks, appending their outcomes.

    Args:
        config: Effective configuration controlling quality enforcement.
        state: Prepared lint state providing discovery context and options.
        run_result: Aggregated run result to extend with quality diagnostics.
        logger: Optional CLI logger used to report appended diagnostics.
    """
    root = state.root
    if run_result.files and (
        config.quality.enforce_in_lint
        or config.severity.sensitivity in _QUALITY_SENSITIVITY_THRESHOLD
    ):
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
        if quality_result.issues:
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
            if diagnostics:
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

    for definition in iter_internal_linters():
        _run_internal_linter(definition, state=state, run_result=run_result, logger=logger)


def _quality_issue_to_diagnostic(issue: QualityIssue, *, root: Path) -> Diagnostic | None:
    """Convert a quality issue to a lint diagnostic.

    Args:
        issue: Quality issue produced by the checker.
        root: Repository root used to normalise paths.

    Returns:
        Diagnostic | None: Equivalent diagnostic or ``None`` when the issue
        level cannot be mapped to a lint severity.
    """
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
    """Return a human-readable summary for quality issue stdout.

    Args:
        diagnostic: Diagnostic derived from the quality checker.
        location: Normalised file location for display.

    Returns:
        str: Formatted summary string.
    """

    if location:
        return f"[{diagnostic.severity.value}] {location}: {diagnostic.message}"
    return f"[{diagnostic.severity.value}] {diagnostic.message}"


def _merge_discovered_files(run_result: RunResult, files: tuple[Path, ...]) -> None:
    """Extend ``run_result.files`` with files considered by docstring checks."""

    if not files:
        return
    existing = set(run_result.files)
    for file in files:
        if file not in existing:
            run_result.files.append(file)
            existing.add(file)


def _run_internal_linter(
    definition: InternalLinterDefinition,
    *,
    state: PreparedLintState,
    run_result: RunResult,
    logger: CLILogger | None,
) -> None:
    """Run ``definition`` when requested by meta flags or selections."""

    meta_enabled = bool(getattr(state.meta, definition.meta_attribute, False))
    if not meta_enabled and not _selection_triggers_linter(state, definition.selection_tokens):
        return

    report: InternalLintReport = definition.runner(state, emit_to_logger=meta_enabled)
    if report.outcome.stderr and logger is not None and not meta_enabled:
        for warning in report.outcome.stderr:
            logger.warn(warning)
    run_result.outcomes.append(report.outcome)
    _merge_discovered_files(run_result, report.files)


def _selection_triggers_linter(state: PreparedLintState, tokens: tuple[str, ...]) -> bool:
    if not tokens:
        return False
    selection = state.options.selection_options
    normalized_tokens = {token.lower() for token in tokens}
    normalized_only = {value.lower() for value in selection.only}
    normalized_filters = {value.lower() for value in selection.filters}
    return bool(normalized_tokens & normalized_only) or bool(normalized_tokens & normalized_filters)


_QUALITY_SEVERITY_MAP: dict[QualityIssueLevel, Severity] = {
    QualityIssueLevel.ERROR: Severity.ERROR,
    QualityIssueLevel.WARNING: Severity.WARNING,
}


__all__ = ["handle_reporting", "append_internal_quality_checks"]
