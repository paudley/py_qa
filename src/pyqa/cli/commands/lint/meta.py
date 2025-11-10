# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Meta-command helpers for the lint CLI."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pyqa.interfaces.orchestration_selection import SelectionResult
from pyqa.orchestration.selection_context import UnknownToolRequestedError

from ....catalog.errors import CatalogIntegrityError, CatalogValidationError
from ....tools.builtin_registry import initialize_registry
from ....tools.registry import DEFAULT_REGISTRY
from ..doctor.command import run_doctor
from ..tool_info.command import run_tool_info
from .explain import render_explain_tools, write_explain_tools_json
from .fetch import render_fetch_all_tools
from .preparation import PreparedLintState
from .runtime import LintRuntimeContext


@dataclass(slots=True)
class MetaActionOutcome:
    """Describe the result of handling lint meta actions."""

    exit_code: int | None = None
    handled: bool = False


def handle_initial_meta_actions(state: PreparedLintState) -> MetaActionOutcome:
    """Process meta flags that must run before configuration is built.

    Args:
        state: Prepared CLI state containing parsed meta flags and logger.

    Returns:
        MetaActionOutcome: Outcome describing whether a meta action executed and
        which exit code should be used.
    """

    for handler in (
        _handle_doctor_action,
        _handle_validate_schema_action,
    ):
        outcome = handler(state)
        if outcome.handled:
            return outcome
    return MetaActionOutcome()


def handle_runtime_meta_actions(
    runtime: LintRuntimeContext,
    *,
    phase_order: tuple[str, ...],
) -> MetaActionOutcome:
    """Process meta flags that require configuration/runtime context.

    Args:
        runtime: Prepared runtime context containing orchestrator collaborators.
        phase_order: Ordered tuple of lint phases used for fetch summaries.

    Returns:
        MetaActionOutcome: Outcome describing whether a meta action executed and
        which exit code should be used.
    """

    outcome = _handle_explain_tools_action(runtime)
    if outcome.handled:
        return outcome
    outcome = _handle_tool_info_action(runtime)
    if outcome.handled:
        return outcome
    outcome = _handle_fetch_all_tools_action(runtime, phase_order=phase_order)
    return outcome if outcome.handled else MetaActionOutcome()


def _handle_explain_tools_action(runtime: LintRuntimeContext) -> MetaActionOutcome:
    """Render tool-selection diagnostics when requested by the CLI state.

    Args:
        runtime: Runtime context containing orchestrator, configuration, and state.

    Returns:
        MetaActionOutcome: Outcome indicating whether explain mode executed and any exit code.
    """

    meta = runtime.state.meta
    if not meta.explain_tools:
        return MetaActionOutcome()

    orchestrator = runtime.orchestrator
    plan_method = getattr(orchestrator, "plan_tools", None)
    if plan_method is None:
        runtime.state.logger.fail("Current execution pipeline does not support --explain-tools")
        return MetaActionOutcome(exit_code=1, handled=True)

    try:
        selection: SelectionResult = plan_method(runtime.config, root=runtime.state.root)
    except UnknownToolRequestedError as exc:
        runtime.state.logger.fail(str(exc))
        return MetaActionOutcome(exit_code=1, handled=True)
    rows = render_explain_tools(runtime, selection)
    json_target = meta.actions.explain_tools_json
    if json_target:
        write_explain_tools_json(Path(json_target), rows, runtime.state.logger.console)
    return MetaActionOutcome(exit_code=0, handled=True)


def _handle_doctor_action(state: PreparedLintState) -> MetaActionOutcome:
    """Execute the doctor meta-action when requested by the CLI state.

    Args:
        state: Prepared CLI state containing meta flag selections.

    Returns:
        MetaActionOutcome: Outcome describing execution of the doctor action.
    """

    if not state.meta.doctor:
        return MetaActionOutcome()
    return MetaActionOutcome(exit_code=run_doctor(state.root), handled=True)


def _handle_validate_schema_action(state: PreparedLintState) -> MetaActionOutcome:
    """Execute schema validation when requested by the CLI state.

    Args:
        state: Prepared CLI state containing meta flag selections.

    Returns:
        MetaActionOutcome: Outcome describing execution of schema validation.
    """

    if not state.meta.validate_schema:
        return MetaActionOutcome()
    try:
        initialize_registry(registry=DEFAULT_REGISTRY)
    except (CatalogValidationError, CatalogIntegrityError) as exc:
        state.logger.fail(f"Catalog validation failed: {exc}")
        return MetaActionOutcome(exit_code=1, handled=True)
    state.logger.ok("Catalog validation succeeded")
    return MetaActionOutcome(exit_code=0, handled=True)


def _handle_tool_info_action(runtime: LintRuntimeContext) -> MetaActionOutcome:
    """Render tool information when the meta flag requests it.

    Args:
        runtime: Prepared runtime context containing CLI state and catalog.

    Returns:
        MetaActionOutcome: Outcome describing execution of the tool-info action.
    """

    tool_name = runtime.state.meta.actions.tool_info
    if tool_name is None:
        return MetaActionOutcome()
    exit_code = run_tool_info(
        tool_name,
        root=runtime.state.root,
        cfg=runtime.config,
        catalog_snapshot=runtime.catalog_snapshot,
    )
    return MetaActionOutcome(exit_code=exit_code, handled=True)


def _handle_fetch_all_tools_action(
    runtime: LintRuntimeContext,
    *,
    phase_order: tuple[str, ...],
) -> MetaActionOutcome:
    """Prepare all tool runtimes when requested by the CLI state.

    Args:
        runtime: Prepared runtime context containing orchestrator collaborators.
        phase_order: Ordered tuple of lint phases used for summary rendering.

    Returns:
        MetaActionOutcome: Outcome describing execution of the fetch-all action.
    """

    if not runtime.state.meta.fetch_all_tools:
        return MetaActionOutcome()
    exit_code = render_fetch_all_tools(runtime, phase_order=phase_order)
    return MetaActionOutcome(exit_code=exit_code, handled=True)


__all__ = [
    "MetaActionOutcome",
    "handle_initial_meta_actions",
    "handle_runtime_meta_actions",
]
