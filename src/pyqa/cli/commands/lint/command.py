# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Lint command implementation."""

from __future__ import annotations

from typing import Annotated, Final, cast

import typer
from rich.progress import Progress

from pyqa.interfaces.analysis import AnnotationProvider
from pyqa.interfaces.config import Config as ConfigProtocol
from pyqa.interfaces.linting import CLILogger as CLILoggerView
from pyqa.interfaces.linting import PreparedLintState as PreparedLintStateView
from pyqa.interfaces.orchestration_selection import PhaseLiteral
from pyqa.orchestration.selection_context import PHASE_ORDER, UnknownToolRequestedError
from pyqa.runtime.console.manager import detect_tty

from ....config import ConfigError
from ....linting.registry import iter_internal_linters
from ....platform.workspace import is_pyqa_lint_workspace
from ...core.config_builder import build_config
from ...core.runtime import ServiceResolutionError
from ...core.shared import Depends, build_cli_logger
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
    logger: CLILoggerView,
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
    actions = meta.actions
    analysis_checks = meta.analysis
    runtime_checks = meta.runtime

    conflicts = (
        (
            actions.doctor and actions.tool_info is not None,
            "--doctor and --tool-info cannot be combined",
        ),
        (
            actions.doctor and actions.fetch_all_tools,
            "--doctor and --fetch-all-tools cannot be combined",
        ),
        (
            actions.tool_info is not None and actions.fetch_all_tools,
            "--tool-info and --fetch-all-tools cannot be combined",
        ),
        (
            actions.validate_schema and actions.doctor,
            "--validate-schema and --doctor cannot be combined",
        ),
        (
            actions.validate_schema and actions.tool_info is not None,
            "--validate-schema and --tool-info cannot be combined",
        ),
        (
            actions.validate_schema and actions.fetch_all_tools,
            "--validate-schema and --fetch-all-tools cannot be combined",
        ),
        (
            actions.explain_tools and actions.doctor,
            "--explain-tools and --doctor cannot be combined",
        ),
        (
            actions.explain_tools and actions.tool_info is not None,
            "--explain-tools and --tool-info cannot be combined",
        ),
        (
            actions.explain_tools and actions.fetch_all_tools,
            "--explain-tools and --fetch-all-tools cannot be combined",
        ),
        (
            actions.explain_tools and actions.validate_schema,
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
        analysis_checks.check_docstrings,
        analysis_checks.check_suppressions,
        analysis_checks.check_types_strict,
        runtime_checks.core.check_closures,
        runtime_checks.core.check_signatures,
        runtime_checks.core.check_cache_usage,
        runtime_checks.core.check_value_types,
        runtime_checks.core.check_value_types_general,
        runtime_checks.policy.check_license_header,
        runtime_checks.policy.check_copyright,
        runtime_checks.policy.check_python_hygiene,
        runtime_checks.additional.check_file_size,
        runtime_checks.additional.check_schema_sync,
    )
    if any(check_flags) and any(
        (
            actions.doctor,
            actions.tool_info is not None,
            actions.fetch_all_tools,
            actions.validate_schema,
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

    meta_flags = state.meta
    if meta_flags.actions.normal:
        config.quality.enforce_in_lint = True

    pyqa_explicit = meta_flags.runtime.additional.pyqa_rules or meta_flags.actions.normal
    if pyqa_explicit and not config.execution.pyqa_rules:
        config.execution.pyqa_rules = True

    return build_lint_runtime_context(
        cast(PreparedLintStateView, state),
        config=cast(ConfigProtocol, config),
    )


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

    annotation_provider: AnnotationProvider | None = None
    if runtime.services is not None:
        try:
            annotation_provider = cast(
                AnnotationProvider,
                runtime.services.resolve("annotation_provider"),
            )
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


def _handle_unknown_only_error(logger: CLILoggerView, exc: UnknownToolRequestedError) -> None:
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
    """Ensure meta flags translate into internal tool selection.

    Args:
        state: Prepared lint state containing meta flags and selection options.
    """

    selection = state.options.selection_options
    meta = state.meta
    meta_actions = meta.actions
    if meta_actions.normal:
        state.options.with_added_provided(PROVIDED_FLAG_INTERNAL_LINTERS)
        return

    existing = {name.lower() for name in selection.only}
    added = False
    pyqa_enabled = meta.runtime.additional.pyqa_rules or is_pyqa_lint_workspace(state.root)
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
