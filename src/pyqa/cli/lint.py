# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Lint command implementation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import typer
from rich.progress import Progress

from ..config import Config, ConfigError
from ..console import is_tty
from ..discovery import build_default_discovery
from ..execution.orchestrator import Orchestrator, OrchestratorHooks
from ..tooling.catalog.errors import CatalogIntegrityError, CatalogValidationError
from ..tooling.catalog.model_catalog import CatalogSnapshot
from ..tools.builtin_registry import initialize_registry
from ..tools.registry import DEFAULT_REGISTRY
from ._lint_cli_models import (
    ADVICE_HELP,
    BANDIT_CONFIDENCE_HELP,
    BANDIT_SEVERITY_HELP,
    CACHE_DIR_HELP,
    FETCH_ALL_TOOLS_HELP,
    FILTER_HELP,
    JOBS_HELP,
    LINE_LENGTH_HELP,
    MAX_ARGUMENTS_HELP,
    MAX_COMPLEXITY_HELP,
    NORMAL_PRESET_HELP,
    OUTPUT_MODE_CONCISE,
    OUTPUT_MODE_HELP,
    PR_SUMMARY_MIN_SEVERITY_HELP,
    PR_SUMMARY_OUT_HELP,
    PR_SUMMARY_TEMPLATE_HELP,
    PYLINT_FAIL_UNDER_HELP,
    REPORT_JSON_HELP,
    SARIF_HELP,
    SENSITIVITY_HELP,
    SQL_DIALECT_HELP,
    TOOL_INFO_HELP,
    TYPE_CHECKING_HELP,
    STRICT_CONFIG_HELP,
    USE_LOCAL_LINTERS_HELP,
    VALIDATE_SCHEMA_HELP,
    LintCLIInputs,
    PathArgument,
    RootOption,
    _build_advanced_group,
    _build_execution_group,
    _execution_runtime_dependency,
    _build_output_group,
    _build_target_group,
    _git_params_dependency,
    _meta_params_dependency,
    _output_params_dependency,
    _override_params_dependency,
    _path_params_dependency,
    _reporting_params_dependency,
    _selection_params_dependency,
    _severity_params_dependency,
    _summary_params_dependency,
)
from ._lint_preparation import PreparedLintState, prepare_lint_state
from ._lint_fetch import render_fetch_all_tools
from ._lint_progress import ExecutionProgressController
from ._lint_reporting import append_internal_quality_checks, handle_reporting
from .config_builder import build_config
from .doctor import run_doctor
from .tool_info import run_tool_info

PHASE_SORT_ORDER: tuple[str, ...] = (
    "lint",
    "format",
    "analysis",
    "security",
    "test",
    "coverage",
    "utility",
)


@dataclass(slots=True)
class LintRuntimeContext:
    """Bundle runtime dependencies for lint execution."""

    state: PreparedLintState
    config: Config
    orchestrator: Orchestrator
    hooks: OrchestratorHooks
    catalog_snapshot: CatalogSnapshot

def lint_command(
    ctx: typer.Context,
    paths: PathArgument,
    root: RootOption,
    changed_only: Annotated[bool, typer.Option(False, help="Limit to files changed according to git.")],
    diff_ref: Annotated[str, typer.Option("HEAD", help="Git ref for change detection.")],
    include_untracked: Annotated[bool, typer.Option(True, help="Include untracked files during git discovery.")],
    base_branch: Annotated[str | None, typer.Option(None, help="Base branch for merge-base diffing.")],
    paths_from_stdin: Annotated[bool, typer.Option(False, help="Read file paths from stdin.")],
    dirs: Annotated[list[Path], typer.Option([], "--dir", help="Add directory to discovery roots (repeatable).")],
    exclude: Annotated[list[Path], typer.Option([], help="Exclude specific paths or globs.")],
    normal: Annotated[bool, typer.Option(False, "-n", "--normal", help=NORMAL_PRESET_HELP)],
    no_lint_tests: Annotated[
        bool,
        typer.Option(
            False,
            "--no-lint-tests",
            help="Exclude paths containing 'tests' from linting.",
        ),
    ],
    filters: Annotated[list[str], typer.Option([], "--filter", help=FILTER_HELP)],
    only: Annotated[list[str], typer.Option([], help="Run only the selected tool(s).")],
    language: Annotated[list[str], typer.Option([], help="Filter tools by language.")],
    fix_only: Annotated[bool, typer.Option(False, help="Run only fix-capable actions.")],
    check_only: Annotated[bool, typer.Option(False, help="Run only check actions.")],
    verbose: Annotated[bool, typer.Option(False, help="Verbose output.")],
    quiet: Annotated[bool, typer.Option(False, "--quiet", "-q", help="Minimal output.")],
    no_color: Annotated[bool, typer.Option(False, help="Disable ANSI colour output.")],
    no_emoji: Annotated[bool, typer.Option(False, help="Disable emoji output.")],
    output_mode: Annotated[
        str,
        typer.Option(OUTPUT_MODE_CONCISE, "--output", help=OUTPUT_MODE_HELP),
    ],
    show_passing: Annotated[bool, typer.Option(False, help="Include successful diagnostics in output.")],
    no_stats: Annotated[bool, typer.Option(False, help="Suppress summary statistics.")],
    report_json: Annotated[Path | None, typer.Option(None, help=REPORT_JSON_HELP)],
    sarif_out: Annotated[Path | None, typer.Option(None, help=SARIF_HELP)],
    pr_summary_out: Annotated[Path | None, typer.Option(None, help=PR_SUMMARY_OUT_HELP)],
    pr_summary_limit: Annotated[
        int,
        typer.Option(100, "--pr-summary-limit", help="Maximum diagnostics in PR summary."),
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
    jobs: Annotated[int | None, typer.Option(None, "--jobs", "-j", min=1, help=JOBS_HELP)],
    bail: Annotated[bool, typer.Option(False, "--bail", help="Exit on first tool failure.")],
    no_cache: Annotated[bool, typer.Option(False, help="Disable on-disk result caching.")],
    cache_dir: Annotated[Path, typer.Option(Path(".lint-cache"), "--cache-dir", help=CACHE_DIR_HELP)],
    use_local_linters: Annotated[bool, typer.Option(False, "--use-local-linters", help=USE_LOCAL_LINTERS_HELP)],
    strict_config: Annotated[bool, typer.Option(False, "--strict-config", help=STRICT_CONFIG_HELP)],
    line_length: Annotated[int, typer.Option(120, "--line-length", help=LINE_LENGTH_HELP)],
    max_complexity: Annotated[
        int | None,
        typer.Option(None, "--max-complexity", min=1, help=MAX_COMPLEXITY_HELP),
    ],
    max_arguments: Annotated[
        int | None,
        typer.Option(None, "--max-arguments", min=1, help=MAX_ARGUMENTS_HELP),
    ],
    type_checking: Annotated[
        str | None,
        typer.Option(
            None,
            "--type-checking",
            case_sensitive=False,
            help=TYPE_CHECKING_HELP,
        ),
    ],
    bandit_severity: Annotated[
        str | None,
        typer.Option(
            None,
            "--bandit-severity",
            case_sensitive=False,
            help=BANDIT_SEVERITY_HELP,
        ),
    ],
    bandit_confidence: Annotated[
        str | None,
        typer.Option(
            None,
            "--bandit-confidence",
            case_sensitive=False,
            help=BANDIT_CONFIDENCE_HELP,
        ),
    ],
    pylint_fail_under: Annotated[
        float | None,
        typer.Option(None, "--pylint-fail-under", help=PYLINT_FAIL_UNDER_HELP),
    ],
    sensitivity: Annotated[
        str | None,
        typer.Option(
            None,
            "--sensitivity",
            case_sensitive=False,
            help=SENSITIVITY_HELP,
        ),
    ],
    sql_dialect: Annotated[str, typer.Option("postgresql", "--sql-dialect", help=SQL_DIALECT_HELP)],
    doctor: Annotated[bool, typer.Option(False, "--doctor", help="Run environment diagnostics and exit.")],
    tool_info: Annotated[str | None, typer.Option(None, "--tool-info", metavar="TOOL", help=TOOL_INFO_HELP)],
    fetch_all_tools: Annotated[bool, typer.Option(False, "--fetch-all-tools", help=FETCH_ALL_TOOLS_HELP)],
    advice: Annotated[bool, typer.Option(False, "--advice", help=ADVICE_HELP)],
    validate_schema: Annotated[bool, typer.Option(False, "--validate-schema", help=VALIDATE_SCHEMA_HELP)],
) -> None:
    """Typer entry point for the ``pyqa lint`` command."""

    path_params = _path_params_dependency(paths, root, paths_from_stdin, dirs, exclude)
    git_params = _git_params_dependency(changed_only, diff_ref, include_untracked, base_branch, no_lint_tests)
    selection_params = _selection_params_dependency(filters, only, language, fix_only, check_only)
    runtime_params = _execution_runtime_dependency(jobs, bail, no_cache, cache_dir, use_local_linters)
    output_params = _output_params_dependency(verbose, quiet, no_color, no_emoji, output_mode)
    reporting_params = _reporting_params_dependency(show_passing, no_stats, report_json, sarif_out, pr_summary_out)
    summary_params = _summary_params_dependency(pr_summary_limit, pr_summary_min_severity, pr_summary_template, advice)
    override_params = _override_params_dependency(line_length, sql_dialect, max_complexity, max_arguments, type_checking)
    severity_params = _severity_params_dependency(bandit_severity, bandit_confidence, pylint_fail_under, sensitivity)
    meta_params = _meta_params_dependency(doctor, tool_info, fetch_all_tools, validate_schema, normal)

    inputs = LintCLIInputs(
        targets=_build_target_group(path_params, git_params),
        execution=_build_execution_group(selection_params, runtime_params, strict_config),
        output=_build_output_group(output_params, reporting_params, summary_params),
        advanced=_build_advanced_group(override_params, severity_params, meta_params),
    )

    _execute_lint(ctx, inputs)


def _execute_lint(ctx: typer.Context, inputs: LintCLIInputs) -> None:
    """Resolve CLI arguments into structured inputs and run the pipeline."""

    _validate_cli_combinations(inputs)
    state = prepare_lint_state(ctx, inputs)
    _run_early_meta_actions(state)
    runtime = _build_runtime_context(state)
    exit_code = _dispatch_meta_commands(runtime)
    if exit_code is not None:
        raise typer.Exit(code=exit_code)
    _run_lint_pipeline(runtime)


def _validate_cli_combinations(inputs: LintCLIInputs) -> None:
    """Guard against unsupported flag combinations before heavy processing."""

    meta = inputs.advanced.meta
    selection = inputs.execution.selection
    rendering = inputs.output.rendering

    conflicts = (
        (
            meta.doctor and meta.tool_info is not None,
            "--doctor and --tool-info cannot be combined",
        ),
        (
            meta.doctor and meta.fetch_all_tools,
            "--doctor and --fetch-all-tools cannot be combined",
        ),
        (
            meta.tool_info is not None and meta.fetch_all_tools,
            "--tool-info and --fetch-all-tools cannot be combined",
        ),
        (
            meta.validate_schema and meta.doctor,
            "--validate-schema and --doctor cannot be combined",
        ),
        (
            meta.validate_schema and meta.tool_info is not None,
            "--validate-schema and --tool-info cannot be combined",
        ),
        (
            meta.validate_schema and meta.fetch_all_tools,
            "--validate-schema and --fetch-all-tools cannot be combined",
        ),
        (
            selection.fix_only and selection.check_only,
            "--fix-only and --check-only are mutually exclusive",
        ),
        (
            rendering.verbose and rendering.quiet,
            "--verbose and --quiet cannot be combined",
        ),
    )
    for condition, message in conflicts:
        if condition:
            raise typer.BadParameter(message)


def _run_early_meta_actions(state: PreparedLintState) -> None:
    """Handle early-exit meta commands before configuration work."""

    meta = state.meta
    if meta.doctor:
        exit_code = run_doctor(state.root)
        raise typer.Exit(code=exit_code)

    if meta.validate_schema:
        try:
            initialize_registry(registry=DEFAULT_REGISTRY)
        except (CatalogValidationError, CatalogIntegrityError) as exc:
            typer.echo(f"Catalog validation failed: {exc}", err=True)
            raise typer.Exit(code=1) from exc
        typer.echo("Catalog validation succeeded")
        raise typer.Exit(code=0)


def _build_runtime_context(state: PreparedLintState) -> LintRuntimeContext:
    """Materialise runtime dependencies for lint execution."""

    try:
        config = build_config(state.options)
    except (ValueError, ConfigError) as exc:
        raise typer.BadParameter(str(exc)) from exc

    catalog_snapshot = initialize_registry(registry=DEFAULT_REGISTRY)
    hooks = OrchestratorHooks()
    orchestrator = Orchestrator(
        registry=DEFAULT_REGISTRY,
        discovery=build_default_discovery(),
        hooks=hooks,
    )
    return LintRuntimeContext(
        state=state,
        config=config,
        orchestrator=orchestrator,
        hooks=hooks,
        catalog_snapshot=catalog_snapshot,
    )


def _dispatch_meta_commands(runtime: LintRuntimeContext) -> int | None:
    """Execute meta commands that rely on configuration and registry state."""

    meta = runtime.state.meta
    if meta.tool_info is not None:
        return run_tool_info(
            meta.tool_info,
            root=runtime.state.root,
            cfg=runtime.config,
            catalog_snapshot=runtime.catalog_snapshot,
        )
    if meta.fetch_all_tools:
        return render_fetch_all_tools(runtime, phase_order=PHASE_SORT_ORDER)
    return None


def _run_lint_pipeline(runtime: LintRuntimeContext) -> None:
    """Execute linting via the orchestrator and manage reporting."""

    config = runtime.config
    controller = ExecutionProgressController(
        runtime,
        is_terminal=is_tty(),
        progress_factory=Progress,
    )
    controller.install(runtime.hooks)

    result = runtime.orchestrator.run(config, root=runtime.state.root)
    append_internal_quality_checks(
        config=config,
        root=runtime.state.root,
        run_result=result,
    )

    controller.advance_rendering_phase()

    final_summary = controller.finalize(not result.failed)
    if final_summary and controller.console is not None:
        controller.console.print(final_summary)
    controller.stop()

    handle_reporting(
        result,
        config,
        runtime.state.artifacts.report_json,
        runtime.state.artifacts.sarif_out,
        runtime.state.artifacts.pr_summary_out,
    )
    raise typer.Exit(code=1 if result.failed else 0)


# Backwards compatibility ------------------------------------------------------

_append_internal_quality_checks = append_internal_quality_checks
_handle_reporting = handle_reporting
