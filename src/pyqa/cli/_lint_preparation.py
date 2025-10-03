# SPDX-License-Identifier: MIT
"""Services for preparing lint command state from CLI inputs."""

from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import typer

from ..config import default_parallel_jobs
from ..constants import PY_QA_DIR_NAME
from ..filesystem.paths import normalize_path
from ..workspace import is_py_qa_workspace
from ._lint_cli_models import (
    OUTPUT_MODE_CONCISE,
    LintCLIInputs,
)
from ._lint_cli_models import LintDisplayOptions as CLIDisplayOptions
from ._lint_cli_models import (
    LintExecutionRuntimeParams,
    LintMetaParams,
    LintOutputArtifacts,
    LintOutputParams,
    LintPathParams,
    LintReportingParams,
    OutputModeLiteral,
)
from .options import (
    ExecutionFormattingOptions,
    ExecutionRuntimeOptions,
    LintComplexityOptions,
)
from .options import LintDisplayOptions as OptionsDisplayOptions
from .options import (
    LintExecutionOptions,
    LintGitOptions,
    LintOptions,
    LintOutputBundle,
    LintOverrideOptions,
    LintSelectionOptions,
    LintSeverityOptions,
    LintStrictnessOptions,
    LintSummaryOptions,
    LintTargetOptions,
)
from .shared import CLILogger
from .utils import filter_py_qa_paths


@dataclass(slots=True)
class PreparedLintState:
    """Contain normalized inputs and metadata required to execute linting."""

    options: LintOptions
    meta: LintMetaParams
    root: Path
    ignored_py_qa: list[str]
    artifacts: LintOutputArtifacts
    display: CLIDisplayOptions
    logger: CLILogger


@dataclass(slots=True)
class NormalizedTargets:
    """Hold normalized path parameters and derived root information."""

    root: Path
    paths: list[Path]
    dirs: list[Path]
    exclude: list[Path]
    ignored_py_qa: list[str]


@dataclass(slots=True)
class NormalPresetResult:
    """Store preset adjustments applied to options and flags."""

    output_mode: OutputModeLiteral
    advice: bool
    no_lint_tests: bool
    use_local_linters: bool
    exclude_paths: list[Path]
    provided_flags: set[str]


@dataclass(slots=True)
class NormalPresetState:
    """Encapsulate mutable preset fields prior to adjustments."""

    output_mode: OutputModeLiteral
    advice: bool
    no_lint_tests: bool
    use_local_linters: bool
    exclude_paths: list[Path]
    provided_flags: set[str]


def prepare_lint_state(
    ctx: typer.Context,
    inputs: LintCLIInputs,
    *,
    logger: CLILogger,
) -> PreparedLintState:
    """Normalise CLI inputs and construct the options dataclass."""

    targets = inputs.targets
    execution = inputs.execution
    output = inputs.output
    advanced = inputs.advanced

    rendering = output.rendering
    reporting = output.reporting
    summary = output.summary
    overrides = advanced.overrides
    severity = advanced.severity
    meta = advanced.meta

    invocation_cwd = Path.cwd()
    normalized_targets = _normalize_targets(
        ctx,
        targets.path,
        invocation_cwd=invocation_cwd,
        logger=logger,
    )
    artifacts = _resolve_artifacts(reporting, invocation_cwd=invocation_cwd)
    display = _build_display_options(rendering)
    cache_dir = normalize_path(execution.runtime.cache_dir, base_dir=invocation_cwd)
    effective_jobs = _effective_jobs(execution.runtime)

    _validate_pylint_fail_under(severity.pylint_fail_under)

    provided = _collect_provided_flags(
        ctx,
        paths_provided=bool(normalized_targets.paths),
        dirs=normalized_targets.dirs,
        exclude=normalized_targets.exclude,
        filters=execution.selection.filters,
        only=execution.selection.only,
        language=execution.selection.language,
    )

    preset_state = NormalPresetState(
        output_mode=rendering.output_mode,
        advice=summary.advice,
        no_lint_tests=targets.git.no_lint_tests,
        use_local_linters=execution.runtime.use_local_linters,
        exclude_paths=normalized_targets.exclude,
        provided_flags=provided,
    )
    preset = _apply_normal_preset(meta=meta, state=preset_state)

    options = LintOptions(
        targets=LintTargetOptions(
            root=normalized_targets.root,
            paths=list(normalized_targets.paths),
            dirs=list(normalized_targets.dirs),
            exclude=preset.exclude_paths,
            paths_from_stdin=targets.path.paths_from_stdin,
        ),
        git=LintGitOptions(
            changed_only=targets.git.changed_only,
            diff_ref=targets.git.diff_ref,
            include_untracked=targets.git.include_untracked,
            base_branch=targets.git.base_branch,
            no_lint_tests=preset.no_lint_tests,
        ),
        selection=LintSelectionOptions(
            filters=list(execution.selection.filters),
            only=list(execution.selection.only),
            language=list(execution.selection.language),
            fix_only=execution.selection.fix_only,
            check_only=execution.selection.check_only,
        ),
        output=LintOutputBundle(
            display=OptionsDisplayOptions(
                verbose=display.verbose,
                quiet=display.quiet,
                no_color=rendering.no_color,
                no_emoji=rendering.no_emoji,
                output_mode=preset.output_mode,
                advice=preset.advice,
            ),
            summary=LintSummaryOptions(
                show_passing=reporting.show_passing,
                no_stats=reporting.no_stats,
                pr_summary_out=artifacts.pr_summary_out,
                pr_summary_limit=summary.pr_summary_limit,
                pr_summary_min_severity=summary.pr_summary_min_severity,
                pr_summary_template=summary.pr_summary_template,
            ),
        ),
        execution=LintExecutionOptions(
            runtime=ExecutionRuntimeOptions(
                jobs=effective_jobs,
                bail=execution.runtime.bail,
                no_cache=execution.runtime.no_cache,
                cache_dir=cache_dir,
                use_local_linters=preset.use_local_linters,
                strict_config=execution.runtime.strict_config,
            ),
            formatting=ExecutionFormattingOptions(
                line_length=overrides.line_length,
                sql_dialect=overrides.sql_dialect,
                python_version=overrides.python_version,
            ),
        ),
        overrides=LintOverrideOptions(
            complexity=LintComplexityOptions(
                max_complexity=overrides.max_complexity,
                max_arguments=overrides.max_arguments,
            ),
            strictness=LintStrictnessOptions(
                type_checking=overrides.type_checking,
            ),
            severity=LintSeverityOptions(
                bandit_severity=severity.bandit_severity,
                bandit_confidence=severity.bandit_confidence,
                pylint_fail_under=severity.pylint_fail_under,
                sensitivity=severity.sensitivity,
            ),
        ),
        provided=preset.provided_flags,
    )

    return PreparedLintState(
        options=options,
        meta=meta,
        root=normalized_targets.root,
        ignored_py_qa=normalized_targets.ignored_py_qa,
        artifacts=artifacts,
        display=display,
        logger=logger,
    )


# Internal helpers --------------------------------------------------------------------


def _normalize_targets(
    ctx: typer.Context,
    params: LintPathParams,
    *,
    invocation_cwd: Path,
    logger: CLILogger,
) -> NormalizedTargets:
    paths = _normalize_path_iter(params.paths, invocation_cwd)
    dirs = _normalize_path_iter(params.dirs, invocation_cwd)
    exclude = _normalize_path_iter(params.exclude, invocation_cwd)

    root_source = _parameter_source_name(ctx, "root")
    root = normalize_path(params.root, base_dir=invocation_cwd)
    if root_source in {"DEFAULT", "DEFAULT_MAP"} and paths:
        derived_root = _derive_default_root(paths)
        if derived_root is not None:
            root = derived_root

    ignored_py_qa: list[str] = []
    if not is_py_qa_workspace(root) and paths:
        paths, ignored_py_qa = filter_py_qa_paths(paths, root)
        if ignored_py_qa:
            unique = ", ".join(dict.fromkeys(ignored_py_qa))
            warning_message = (
                f"Ignoring path(s) {unique}: '{PY_QA_DIR_NAME}' directories are skipped "
                "unless lint runs inside the py_qa workspace."
            )
            logger.warn(warning_message)

    return NormalizedTargets(
        root=root,
        paths=paths,
        dirs=dirs,
        exclude=exclude,
        ignored_py_qa=ignored_py_qa,
    )


def _resolve_artifacts(
    reporting: LintReportingParams,
    *,
    invocation_cwd: Path,
) -> LintOutputArtifacts:
    def _normalize(value: Path | None) -> Path | None:
        if value is None:
            return None
        return _normalize_path(value, invocation_cwd)

    return LintOutputArtifacts(
        report_json=_normalize(reporting.report_json),
        sarif_out=_normalize(reporting.sarif_out),
        pr_summary_out=_normalize(reporting.pr_summary_out),
    )


def _build_display_options(rendering: LintOutputParams) -> CLIDisplayOptions:
    return CLIDisplayOptions(
        no_emoji=rendering.no_emoji,
        quiet=rendering.quiet,
        verbose=rendering.verbose,
    )


def _effective_jobs(runtime: LintExecutionRuntimeParams) -> int:
    return runtime.jobs if runtime.jobs is not None else default_parallel_jobs()


def _apply_normal_preset(
    *,
    meta: LintMetaParams,
    state: NormalPresetState,
) -> NormalPresetResult:
    updated_exclude = list(state.exclude_paths)
    updated_provided = set(state.provided_flags)
    effective_output = state.output_mode
    effective_advice = state.advice
    effective_no_lint_tests = state.no_lint_tests
    effective_use_local_linters = state.use_local_linters

    if meta.normal:
        if "output_mode" not in updated_provided:
            effective_output = OUTPUT_MODE_CONCISE
        effective_advice = True
        effective_no_lint_tests = True
        effective_use_local_linters = True
        updated_provided.update(
            {
                "output_mode",
                "advice",
                "exclude",
                "use_local_linters",
                "no_lint_tests",
            },
        )

    if effective_no_lint_tests:
        tests_path = Path("tests")
        if tests_path not in updated_exclude:
            updated_exclude.append(tests_path)
        updated_provided.add("exclude")

    return NormalPresetResult(
        output_mode=effective_output,
        advice=effective_advice,
        no_lint_tests=effective_no_lint_tests,
        use_local_linters=effective_use_local_linters,
        exclude_paths=updated_exclude,
        provided_flags=updated_provided,
    )


def _validate_pylint_fail_under(value: float | None) -> None:
    if value is None:
        return
    if not 0 <= value <= 10:
        raise typer.BadParameter("--pylint-fail-under must be between 0 and 10")


def _normalize_path(path: Path, invocation_cwd: Path) -> Path:
    return normalize_path(path, base_dir=invocation_cwd)


def _normalize_path_iter(values: Iterable[Path], invocation_cwd: Path) -> list[Path]:
    return [normalize_path(value, base_dir=invocation_cwd) for value in values]


def _collect_provided_flags(
    ctx: typer.Context,
    *,
    paths_provided: bool,
    dirs: list[Path],
    exclude: list[Path],
    filters: list[str],
    only: list[str],
    language: list[str],
) -> set[str]:
    tracked = {
        "changed_only",
        "diff_ref",
        "include_untracked",
        "base_branch",
        "paths_from_stdin",
        "dirs",
        "exclude",
        "filters",
        "only",
        "language",
        "normal",
        "fix_only",
        "check_only",
        "verbose",
        "quiet",
        "no_color",
        "no_emoji",
        "no_stats",
        "output_mode",
        "show_passing",
        "jobs",
        "bail",
        "no_cache",
        "cache_dir",
        "pr_summary_out",
        "pr_summary_limit",
        "pr_summary_min_severity",
        "pr_summary_template",
        "use_local_linters",
        "line_length",
        "max_complexity",
        "max_arguments",
        "type_checking",
        "bandit_severity",
        "bandit_confidence",
        "pylint_fail_under",
        "sensitivity",
        "sql_dialect",
        "advice",
    }
    provided: set[str] = set()
    for name in tracked:
        source = _parameter_source_name(ctx, name)
        if source not in {"DEFAULT", "DEFAULT_MAP", None}:
            provided.add(name)
    if paths_provided:
        provided.add("paths")
    if dirs:
        provided.add("dirs")
    if exclude:
        provided.add("exclude")
    if filters:
        provided.add("filters")
    if only:
        provided.add("only")
    if language:
        provided.add("language")
    return provided


def _parameter_source_name(ctx: typer.Context, name: str) -> str | None:
    getter = getattr(ctx, "get_parameter_source", None)
    if not callable(getter):
        return None
    try:
        source = getter(name)
    except TypeError:
        return None
    if source is None:
        return None
    label = getattr(source, "name", None)
    return label if isinstance(label, str) else str(source)


def _derive_default_root(paths: list[Path]) -> Path | None:
    if not paths:
        return None
    candidates = [path if path.is_dir() else path.parent for path in paths]
    if not candidates:
        return None
    common = Path(os.path.commonpath([str(candidate) for candidate in candidates]))
    return common.resolve()


__all__ = [
    "PreparedLintState",
    "prepare_lint_state",
]
