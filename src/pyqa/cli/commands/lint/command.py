# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Lint command implementation."""

from __future__ import annotations

from typing import Annotated, Final

import typer
from rich.progress import Progress

from pyqa.interfaces.core import detect_tty
from pyqa.interfaces.orchestration_selection import PHASE_ORDER, PhaseLiteral, UnknownToolRequestedError

from ....config import ConfigError
from ....linting.registry import iter_internal_linters
from ....platform.workspace import is_py_qa_workspace
from ...core.config_builder import build_config
from ...core.runtime import ServiceResolutionError
from ...core.shared import CLILogger, Depends, build_cli_logger
from .cli_models import _build_lint_cli_inputs
from .meta import (
    MetaActionOutcome,
    handle_initial_meta_actions,
    handle_runtime_meta_actions,
)
from .params import LintCLIInputs
from .preparation import PROVIDED_FLAG_INTERNAL_LINTERS, PreparedLintState, prepare_lint_state
from .progress import ExecutionProgressController
from .reporting import handle_reporting
from .runtime import LintRuntimeContext, build_lint_runtime_context

LintPhaseLiteral = PhaseLiteral

PHASE_SORT_ORDER: Final[tuple[LintPhaseLiteral, ...]] = PHASE_ORDER


def lint_command(
    ctx: typer.Context,
    inputs: Annotated[LintCLIInputs, Depends(_build_lint_cli_inputs)],
) -> None:
    """Typer entry point for the ``pyqa lint`` command.

    Args:
        ctx: Typer context for the current command invocation.
        inputs: Structured CLI inputs produced by dependency factories.
    """
    logger = build_cli_logger(
        emoji=not inputs.output.rendering.no_emoji,
        debug=inputs.output.rendering.debug,
        no_color=inputs.output.rendering.no_color,
    )
    _execute_lint(ctx, inputs, logger=logger)


def _execute_lint(
    ctx: typer.Context,
    inputs: LintCLIInputs,
    *,
    logger: CLILogger,
) -> None:
    """Resolve CLI arguments into structured inputs and run the pipeline.

    Args:
        ctx: Typer context for the current command invocation.
        inputs: Structured CLI inputs produced by dependency factories.
        logger: CLI logger used for user-facing output.
    """
    _validate_cli_combinations(inputs)
    state = prepare_lint_state(ctx, inputs, logger=logger)
    _activate_internal_linters(state)
    early_meta = handle_initial_meta_actions(state)
    _exit_if_handled(early_meta)
    runtime = _build_runtime_context(state)
    runtime_meta = handle_runtime_meta_actions(runtime, phase_order=PHASE_SORT_ORDER)
    _exit_if_handled(runtime_meta)
    _run_lint_pipeline(runtime)


def _validate_cli_combinations(inputs: LintCLIInputs) -> None:
    """Guard against unsupported flag combinations before heavy processing.

    Args:
        inputs: Structured CLI inputs to validate.

    Raises:
        typer.BadParameter: If incompatible flag combinations are detected.
    """
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
            meta.explain_tools and meta.doctor,
            "--explain-tools and --doctor cannot be combined",
        ),
        (
            meta.explain_tools and meta.tool_info is not None,
            "--explain-tools and --tool-info cannot be combined",
        ),
        (
            meta.explain_tools and meta.fetch_all_tools,
            "--explain-tools and --fetch-all-tools cannot be combined",
        ),
        (
            meta.explain_tools and meta.validate_schema,
            "--explain-tools and --validate-schema cannot be combined",
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

    check_flags = (
        meta.check_docstrings,
        meta.check_suppressions,
        meta.check_types_strict,
        meta.check_closures,
        meta.check_signatures,
        meta.check_cache_usage,
        meta.check_value_types,
        meta.check_license_header,
        meta.check_copyright,
        meta.check_python_hygiene,
        meta.check_file_size,
        meta.check_schema_sync,
    )
    if any(check_flags) and any(
        (
            meta.doctor,
            meta.tool_info is not None,
            meta.fetch_all_tools,
            meta.validate_schema,
        ),
    ):
        raise typer.BadParameter("Internal lint check flags cannot be combined with other meta actions")


def _build_runtime_context(state: PreparedLintState) -> LintRuntimeContext:
    """Materialise runtime dependencies for lint execution.

    Args:
        state: Prepared lint state derived from CLI inputs.

    Returns:
        LintRuntimeContext: Runtime bundle required for lint execution.

    Raises:
        typer.BadParameter: If configuration loading fails.
    """
    try:
        config = build_config(state.options)
    except (ValueError, ConfigError) as exc:
        raise typer.BadParameter(str(exc)) from exc

    if state.meta.normal:
        config.quality.enforce_in_lint = True

    pyqa_explicit = state.meta.pyqa_rules or state.meta.normal
    if pyqa_explicit and not config.execution.pyqa_rules:
        config.execution = config.execution.model_copy(update={"pyqa_rules": True})

    return build_lint_runtime_context(state, config=config)


def _run_lint_pipeline(runtime: LintRuntimeContext) -> None:
    """Execute linting via the orchestrator and manage reporting.

    Args:
        runtime: Fully prepared runtime context containing collaborators.

    Raises:
        typer.Exit: Terminates the command with the orchestrator exit status.
    """
    config = runtime.config
    controller = ExecutionProgressController(
        runtime,
        is_terminal=detect_tty(),
        progress_factory=Progress,
    )
    controller.install(runtime.hooks)

    try:
        result = runtime.orchestrator.run(config, root=runtime.state.root)
    except UnknownToolRequestedError as exc:
        _handle_unknown_only_error(runtime.state.logger, exc)
        controller.stop()
        raise typer.Exit(code=1) from exc

    controller.advance_rendering_phase()

    issues_present = result.has_failures() or result.has_diagnostics()
    final_summary = controller.finalize(not issues_present)
    if final_summary and controller.console is not None:
        controller.console.print(final_summary)
    controller.stop()

    annotation_provider = None
    if runtime.services is not None:
        try:
            annotation_provider = runtime.services.resolve("annotation_provider")
        except ServiceResolutionError:
            annotation_provider = None

    handle_reporting(
        result,
        config,
        runtime.state.artifacts,
        logger=runtime.state.logger,
        annotation_provider=annotation_provider,
    )
    raise typer.Exit(code=1 if issues_present else 0)


def _handle_unknown_only_error(logger: CLILogger, exc: UnknownToolRequestedError) -> None:
    """Log a fatal error when ``--only`` references unknown tools.

    Args:
        logger: CLI logger used to render the fatal message.
        exc: Exception containing the missing tool identifiers.
    """

    logger.fail(str(exc))


def _exit_if_handled(outcome: MetaActionOutcome) -> None:
    """Exit the Typer command when ``outcome`` indicates handling occurred.

    Args:
        outcome: Meta action result describing whether handling occurred.

    Raises:
        typer.Exit: Raised when the meta action produced an explicit exit code.
    """
    if not outcome.handled:
        return
    code = outcome.exit_code if outcome.exit_code is not None else 0
    raise typer.Exit(code=code)


# Backwards compatibility ------------------------------------------------------

_handle_reporting = handle_reporting


def _activate_internal_linters(state: PreparedLintState) -> None:
    """Ensure meta flags translate into internal tool selection."""

    selection = state.options.selection_options
    meta = state.meta
    if meta.normal:
        state.options.with_added_provided(PROVIDED_FLAG_INTERNAL_LINTERS)
        return

    existing = {name.lower() for name in selection.only}
    added = False
    pyqa_enabled = meta.pyqa_rules or is_py_qa_workspace(state.root)
    for definition in iter_internal_linters():
        if definition.pyqa_scoped and not pyqa_enabled:
            continue
        attribute = definition.meta_attribute
        if attribute and getattr(meta, attribute, False):
            if definition.name.lower() not in existing:
                selection.only.append(definition.name)
                existing.add(definition.name.lower())
                added = True
    if added:
        state.options.with_added_provided("only", PROVIDED_FLAG_INTERNAL_LINTERS)
