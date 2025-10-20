# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Private helpers that support orchestrator pipelines."""

from __future__ import annotations

import inspect
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from subprocess import CompletedProcess
from typing import Final, Literal, cast

from pyqa.core.environment.tool_env import CommandPreparationRequest, CommandPreparer, PreparedCommand
from pyqa.core.runtime.process import CommandOptions, CommandOverrideMapping

from ..analysis.services import AnnotationProvider, ContextResolver, FunctionScaleEstimator
from ..config import Config
from ..discovery.base import SupportsDiscovery
from ..tools import Tool, ToolContext
from ..tools.registry import ToolRegistry
from .action_executor import (
    ActionExecutor,
    ExecutionEnvironment,
    ExecutionState,
    RunnerCallable,
    wrap_runner,
)
from .tool_selection import ToolSelector
from .worker import run_command

FetchEvent = Literal["start", "completed", "error"]
ActionDecision = Literal["execute", "skip", "bail"]
ToolDecisionAction = Literal["run", "skip"]
_DECISION_EXECUTE: Final[ActionDecision] = "execute"
_DECISION_SKIP: Final[ActionDecision] = "skip"
_DECISION_BAIL: Final[ActionDecision] = "bail"
_FETCH_EVENT_START: Final[FetchEvent] = "start"
_FETCH_EVENT_COMPLETED: Final[FetchEvent] = "completed"
_FETCH_EVENT_ERROR: Final[FetchEvent] = "error"
_TOOL_DECISION_SKIP: Final[ToolDecisionAction] = "skip"

CommandPreparationFn = Callable[[CommandPreparationRequest], PreparedCommand]
FetchCallback = Callable[[FetchEvent, str, str, int, int, str | None], None]


@dataclass(slots=True)
class _LegacyPreparerAdapter:
    """Adapter that converts legacy preparer signatures into request-aware callables."""

    legacy_callable: Callable[..., PreparedCommand]

    def __call__(self, request: CommandPreparationRequest) -> PreparedCommand:
        """Invoke ``legacy_callable`` using fields extracted from ``request``.

        Args:
            request: Dataclass describing the command preparation inputs.

        Returns:
            PreparedCommand: Prepared command produced by the legacy callable.
        """

        return self.legacy_callable(
            tool=request.tool,
            base_cmd=list(request.command),
            root=request.root,
            cache_dir=request.cache_dir,
            system_preferred=request.system_preferred,
            use_local_override=request.use_local_override,
        )


@dataclass(frozen=True, slots=True)
class _ToolingPipeline:
    """Bundle tool selection, execution, and preparation helpers."""

    selector: ToolSelector
    executor: ActionExecutor
    prepare_command: CommandPreparationFn


@dataclass(slots=True)
class _AnalysisProviders:
    """Group annotation and analysis services required by the orchestrator."""

    annotation: AnnotationProvider
    function_scale: FunctionScaleEstimator
    context_resolver: ContextResolver


@dataclass(frozen=True, slots=True)
class _RuntimeContext:
    """Internal container bundling registry and discovery collaborators."""

    registry: ToolRegistry
    discovery: SupportsDiscovery


@dataclass(slots=True)
class _ActionLoopContext:
    """Immutable data required to process an individual tool action."""

    cfg: Config
    environment: ExecutionEnvironment
    state: ExecutionState
    tool: Tool
    tool_context: ToolContext
    preparation: PreparationInputs


class _ActionPlanOutcome(Enum):
    """Result of planning or executing a tool action."""

    CONTINUE = auto()
    BAIL = auto()


@dataclass(frozen=True)
class PreparationResult:
    """Outcome of preparing a single tool action."""

    tool: str
    action: str
    prepared: PreparedCommand | None
    error: str | None


@dataclass(frozen=True)
class PreparationInputs:
    """Shared preparation parameters for tool actions."""

    root: Path
    cache_dir: Path
    system_preferred: bool
    use_local_override: bool


def resolve_preparer(
    preparer: CommandPreparer | CommandPreparationFn | Callable[..., PreparedCommand],
) -> Callable[..., PreparedCommand]:
    """Return a callable capable of preparing commands.

    Args:
        preparer: Instance or callable responsible for preparing commands.

    Returns:
        Callable[..., PreparedCommand]: Callable form of the preparer.

    Raises:
        TypeError: If ``preparer`` is not callable.
    """

    if isinstance(preparer, CommandPreparer):
        return preparer.prepare_request
    prepare_method = getattr(preparer, "prepare", None)
    if callable(prepare_method):
        return cast(Callable[..., PreparedCommand], prepare_method)
    if callable(preparer):
        return cast(Callable[..., PreparedCommand], preparer)
    raise TypeError("cmd_preparer must be callable or expose a callable 'prepare' attribute")


def coerce_preparer(
    prepare_callable: Callable[..., PreparedCommand],
) -> CommandPreparationFn:
    """Convert ``prepare_callable`` into the modern preparer signature.

    Args:
        prepare_callable: Callable returned by :func:`resolve_preparer`.

    Returns:
        CommandPreparationFn: Callable accepting a :class:`CommandPreparationRequest`.
    """

    try:
        signature = inspect.signature(prepare_callable)
    except (TypeError, ValueError):
        signature = None
    if signature is not None:
        parameters = list(signature.parameters.values())
        if len(parameters) == 1 and parameters[0].kind in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        ):
            return cast(CommandPreparationFn, prepare_callable)
    return wrap_legacy_preparer(prepare_callable)


def wrap_legacy_preparer(
    legacy_callable: Callable[..., PreparedCommand],
) -> CommandPreparationFn:
    """Wrap legacy preparers that expect discrete arguments.

    Args:
        legacy_callable: Legacy callable expecting discrete parameters.

    Returns:
        CommandPreparationFn: Adapter that builds a request from legacy inputs.
    """

    return _LegacyPreparerAdapter(legacy_callable=legacy_callable)


def build_default_runner() -> RunnerCallable:
    """Return a runner compatible with :class:`ActionExecutor`.

    Returns:
        RunnerCallable: Callable that delegates to :func:`run_command`.
    """

    def _runner(
        cmd: Sequence[str],
        *,
        options: CommandOptions | None = None,
        overrides: CommandOverrideMapping | None = None,
    ) -> CompletedProcess[str]:
        """Execute ``cmd`` using :func:`run_command` while honouring overrides.

        Args:
            cmd: Command sequence forwarded to the worker.
            options: Optional baseline command options.
            overrides: Optional overrides that tweak execution behaviour.

        Returns:
            CompletedProcess[str]: Completed process produced by :func:`run_command`.
        """

        return run_command(cmd, options=options, overrides=overrides)

    return wrap_runner(_runner)


__all__ = [
    "ActionDecision",
    "FetchEvent",
    "FetchCallback",
    "CommandPreparationFn",
    "_ActionLoopContext",
    "_ActionPlanOutcome",
    "_AnalysisProviders",
    "_DECISION_BAIL",
    "_DECISION_EXECUTE",
    "_DECISION_SKIP",
    "_FETCH_EVENT_COMPLETED",
    "_FETCH_EVENT_ERROR",
    "_FETCH_EVENT_START",
    "_TOOL_DECISION_SKIP",
    "_RuntimeContext",
    "_ToolingPipeline",
    "PreparationInputs",
    "PreparationResult",
    "coerce_preparer",
    "build_default_runner",
    "resolve_preparer",
    "wrap_legacy_preparer",
]
