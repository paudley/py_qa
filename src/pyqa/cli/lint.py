# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Lint command implementation."""

from __future__ import annotations

from typing import Annotated

import typer
from rich.progress import Progress

from ..config import ConfigError
from ..console import is_tty
from ._lint_cli_models import LintCLIInputs, _build_lint_cli_inputs
from ._lint_preparation import PreparedLintState, prepare_lint_state
from ._lint_runtime import LintRuntimeContext, build_lint_runtime_context
from ._lint_progress import ExecutionProgressController
from ._lint_reporting import append_internal_quality_checks, handle_reporting
from ._lint_meta import (
    MetaActionOutcome,
    handle_initial_meta_actions,
    handle_runtime_meta_actions,
)
from .config_builder import build_config
from .shared import CLILogger, Depends, build_cli_logger

PHASE_SORT_ORDER: tuple[str, ...] = (
    "lint",
    "format",
    "analysis",
    "security",
    "test",
    "coverage",
    "utility",
)
def lint_command(
    ctx: typer.Context,
    inputs: Annotated[LintCLIInputs, Depends(_build_lint_cli_inputs)],
) -> None:
    """Typer entry point for the ``pyqa lint`` command."""

    logger = build_cli_logger(emoji=not inputs.output.rendering.no_emoji)
    _execute_lint(ctx, inputs, logger=logger)


def _execute_lint(
    ctx: typer.Context,
    inputs: LintCLIInputs,
    *,
    logger: CLILogger,
) -> None:
    """Resolve CLI arguments into structured inputs and run the pipeline."""

    _validate_cli_combinations(inputs)
    state = prepare_lint_state(ctx, inputs, logger=logger)
    early_meta = handle_initial_meta_actions(state)
    _exit_if_handled(early_meta)
    runtime = _build_runtime_context(state)
    runtime_meta = handle_runtime_meta_actions(runtime, phase_order=PHASE_SORT_ORDER)
    _exit_if_handled(runtime_meta)
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


def _build_runtime_context(state: PreparedLintState) -> LintRuntimeContext:
    """Materialise runtime dependencies for lint execution."""

    try:
        config = build_config(state.options)
    except (ValueError, ConfigError) as exc:
        raise typer.BadParameter(str(exc)) from exc

    return build_lint_runtime_context(state, config=config)


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
        logger=runtime.state.logger,
    )

    controller.advance_rendering_phase()

    final_summary = controller.finalize(not result.failed)
    if final_summary and controller.console is not None:
        controller.console.print(final_summary)
    controller.stop()

    handle_reporting(
        result,
        config,
        runtime.state.artifacts,
        logger=runtime.state.logger,
    )
    raise typer.Exit(code=1 if result.failed else 0)


def _exit_if_handled(outcome: MetaActionOutcome) -> None:
    """Exit the Typer command when ``outcome`` indicates handling occurred."""

    if not outcome.handled:
        return
    code = outcome.exit_code if outcome.exit_code is not None else 0
    raise typer.Exit(code=code)


# Backwards compatibility ------------------------------------------------------

_append_internal_quality_checks = append_internal_quality_checks
_handle_reporting = handle_reporting
