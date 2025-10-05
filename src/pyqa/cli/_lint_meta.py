# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Meta-command helpers for the lint CLI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..tooling.catalog.errors import CatalogIntegrityError, CatalogValidationError
from ..tools.builtin_registry import initialize_registry
from ..tools.registry import DEFAULT_REGISTRY
from ._lint_fetch import render_fetch_all_tools
from .doctor import run_doctor
from .tool_info import run_tool_info

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from ._lint_preparation import PreparedLintState
    from ._lint_runtime import LintRuntimeContext


@dataclass(slots=True)
class MetaActionOutcome:
    """Describe the result of handling lint meta actions."""

    exit_code: int | None = None
    handled: bool = False


def handle_initial_meta_actions(state: PreparedLintState) -> MetaActionOutcome:
    """Process meta flags that must run before configuration is built."""

    for handler in (_handle_doctor_action, _handle_validate_schema_action):
        outcome = handler(state)
        if outcome.handled:
            return outcome
    return MetaActionOutcome()


def handle_runtime_meta_actions(
    runtime: LintRuntimeContext,
    *,
    phase_order: tuple[str, ...],
) -> MetaActionOutcome:
    """Process meta flags that require configuration/runtime context."""

    outcome = _handle_tool_info_action(runtime)
    if outcome.handled:
        return outcome
    outcome = _handle_fetch_all_tools_action(runtime, phase_order=phase_order)
    return outcome if outcome.handled else MetaActionOutcome()


def _handle_doctor_action(state: PreparedLintState) -> MetaActionOutcome:
    if not state.meta.doctor:
        return MetaActionOutcome()
    return MetaActionOutcome(exit_code=run_doctor(state.root), handled=True)


def _handle_validate_schema_action(state: PreparedLintState) -> MetaActionOutcome:
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
    meta = runtime.state.meta
    if meta.tool_info is None:
        return MetaActionOutcome()
    exit_code = run_tool_info(
        meta.tool_info,
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
    if not runtime.state.meta.fetch_all_tools:
        return MetaActionOutcome()
    exit_code = render_fetch_all_tools(runtime, phase_order=phase_order)
    return MetaActionOutcome(exit_code=exit_code, handled=True)


__all__ = [
    "MetaActionOutcome",
    "handle_initial_meta_actions",
    "handle_runtime_meta_actions",
]
