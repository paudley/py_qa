# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""High level orchestration for running registered lint tools."""

from __future__ import annotations

import inspect
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from subprocess import CompletedProcess
from types import MappingProxyType
from typing import Final, Literal, cast

from pyqa.core.environment.tool_env import CommandPreparationRequest, CommandPreparer, PreparedCommand

from ..analysis.bootstrap import register_analysis_services
from ..analysis.change_impact import apply_change_impact
from ..analysis.navigator import build_refactor_navigator
from ..analysis.services import (
    resolve_annotation_provider,
    resolve_context_resolver,
    resolve_function_scale_estimator,
)
from ..analysis.suppression import apply_suppression_hints
from ..cache.context import build_cache_context, load_cached_outcome, save_versions, update_tool_version
from ..config import Config
from ..core.logging import warn
from ..core.models import RunResult, ToolOutcome
from ..core.runtime import ServiceContainer, ServiceResolutionError, register_default_services
from ..core.runtime.process import CommandOptions
from ..diagnostics import build_severity_rules, dedupe_outcomes
from ..discovery.base import SupportsDiscovery
from ..interfaces.analysis import AnnotationProvider
from ..tools import Tool, ToolAction, ToolContext
from ..tools.registry import ToolRegistry
from .action_executor import (
    ActionExecutor,
    ActionInvocation,
    ExecutionEnvironment,
    ExecutionState,
    OutcomeRecord,
    RunnerCallable,
    ScheduledAction,
    wrap_runner,
)
from .runtime import discover_files, filter_files_for_tool, prepare_runtime
from .tool_selection import ToolSelector
from .worker import run_command

FetchEvent = Literal["start", "completed", "error"]
ActionDecision = Literal["execute", "skip", "bail"]
_DECISION_EXECUTE: Final[ActionDecision] = "execute"
_DECISION_SKIP: Final[ActionDecision] = "skip"
_DECISION_BAIL: Final[ActionDecision] = "bail"
_FETCH_EVENT_START: Final[FetchEvent] = "start"
_FETCH_EVENT_COMPLETED: Final[FetchEvent] = "completed"
_FETCH_EVENT_ERROR: Final[FetchEvent] = "error"

FetchCallback = Callable[[FetchEvent, str, str, int, int, str | None], None]
CommandPreparationFn = Callable[[CommandPreparationRequest], PreparedCommand]


@dataclass
class OrchestratorHooks:
    """Optional hooks to customise orchestration behaviour."""

    before_tool: Callable[[str], None] | None = None
    after_tool: Callable[[ToolOutcome], None] | None = None
    after_discovery: Callable[[int], None] | None = None
    after_execution: Callable[[RunResult], None] | None = None
    after_plan: Callable[[int], None] | None = None


@dataclass(frozen=True)
class OrchestratorDeps:
    """Dependencies required to construct an :class:`Orchestrator`."""

    registry: ToolRegistry
    discovery: SupportsDiscovery
    runner: RunnerCallable | None = None
    hooks: OrchestratorHooks | None = None
    cmd_preparer: CommandPreparationFn | None = None
    services: ServiceContainer | None = None


@dataclass(frozen=True)
class OrchestratorOverrides:
    """Optional overrides applied when constructing an :class:`Orchestrator`."""

    runner: RunnerCallable | None = None
    hooks: OrchestratorHooks | None = None
    cmd_preparer: CommandPreparationFn | None = None
    services: ServiceContainer | None = None


@dataclass(frozen=True, slots=True)
class _RuntimeContext:
    """Internal container bundling registry and discovery collaborators."""

    registry: ToolRegistry
    discovery: SupportsDiscovery


class Orchestrator:
    """Coordinates discovery, tool selection, and execution."""

    def __init__(
        self,
        deps: OrchestratorDeps | None = None,
        *,
        registry: ToolRegistry | None = None,
        discovery: SupportsDiscovery | None = None,
        overrides: OrchestratorOverrides | None = None,
    ) -> None:
        """Create an orchestrator with the supplied collaborators.

        Args:
            deps: Container bundling orchestrator dependencies.
            registry: Registry that resolves available tools.
            discovery: Strategy used to locate files for analysis.
            runner: Callable used to spawn external tool processes.
            hooks: Optional callbacks invoked throughout execution.
            cmd_preparer: Callable that converts tool actions into runnable commands.
        """

        overrides = overrides or OrchestratorOverrides()
        if deps is not None:
            if any(
                value is not None
                for value in (
                    registry,
                    discovery,
                    overrides.runner,
                    overrides.hooks,
                    overrides.cmd_preparer,
                    overrides.services,
                )
            ):
                raise TypeError("Pass either 'deps' or explicit overrides, not both")
            registry = deps.registry
            discovery = deps.discovery
            final_runner = deps.runner or overrides.runner
            final_hooks = deps.hooks or overrides.hooks
            final_preparer = deps.cmd_preparer or overrides.cmd_preparer
            services = deps.services
        else:
            final_runner = overrides.runner
            final_hooks = overrides.hooks
            final_preparer = overrides.cmd_preparer
            services = overrides.services
        if registry is None or discovery is None:
            raise TypeError("Orchestrator requires 'registry' and 'discovery' dependencies")

        if services is None:
            services = ServiceContainer()
            register_default_services(services)
            register_analysis_services(services)

        self._context = _RuntimeContext(registry=registry, discovery=discovery)
        base_runner = final_runner or _build_default_runner()
        self._runner = base_runner if isinstance(base_runner, RunnerCallable) else wrap_runner(base_runner)
        self._hooks = final_hooks or OrchestratorHooks()
        self._services: ServiceContainer = services
        preparer = final_preparer
        if preparer is None:
            default_preparer = CommandPreparer()
            preparer = default_preparer.prepare_request
        prepare_callable = self._resolve_preparer(preparer)
        self._prepare_command = self._coerce_preparer(prepare_callable)
        self._selector = ToolSelector(self._context.registry)
        self._executor = ActionExecutor(self._runner, self._hooks.after_tool)
        self._annotation_provider: AnnotationProvider = self._resolve_annotation_provider()
        try:
            self._function_scale = resolve_function_scale_estimator(self._services)
        except ServiceResolutionError:
            self._function_scale = resolve_function_scale_estimator()
        try:
            self._context_resolver = resolve_context_resolver(self._services)
        except ServiceResolutionError:
            self._context_resolver = resolve_context_resolver()

    def run(self, cfg: Config, *, root: Path | None = None) -> RunResult:
        """Execute configured tools and aggregate their outcomes."""

        environment, matched_files = self._build_environment(cfg, root)
        state = ExecutionState()
        self._executor.after_tool_hook = self._hooks.after_tool
        self._notify_discovery(len(matched_files))

        tool_names = self._selector.select_tools(cfg, matched_files, environment.root)
        self._notify_plan(tool_names, cfg)

        for name in tool_names:
            if self._process_tool(
                environment=environment,
                tool_name=name,
                matched_files=matched_files,
                state=state,
            ):
                break

        self._executor.execute_scheduled(environment, state)
        outcomes = [state.outcomes[index] for index in sorted(state.outcomes)]
        self._executor.populate_missing_metrics(state, matched_files)
        result = RunResult(
            root=environment.root,
            files=matched_files,
            outcomes=outcomes,
            tool_versions=environment.cache.versions,
            file_metrics=dict(state.file_metrics),
        )
        dedupe_outcomes(
            result,
            cfg.dedupe,
            annotation_provider=self._annotation_provider,
        )
        self._annotation_provider.annotate_run(result)
        apply_suppression_hints(result, self._annotation_provider)
        apply_change_impact(result, context_resolver=self._context_resolver)
        build_refactor_navigator(
            result,
            self._annotation_provider,
            function_scale=self._function_scale,
        )
        if environment.cache.cache and environment.cache.versions_dirty:
            save_versions(environment.cache.cache_dir, environment.cache.versions)
        if self._hooks.after_execution:
            self._hooks.after_execution(result)
        return result

    def fetch_all_tools(
        self,
        cfg: Config,
        *,
        root: Path | None = None,
        callback: FetchCallback | None = None,
    ) -> list[tuple[str, str, PreparedCommand | None, str | None]]:
        """Prepared command metadata for all tools without executing them."""

        root_path = prepare_runtime(root)
        inputs = self._build_preparation_inputs(cfg, root=root_path)
        results: list[tuple[str, str, PreparedCommand | None, str | None]] = []

        for (
            index,
            total,
            tool_name,
            action_name,
            prepared,
            error,
        ) in self._iter_fetch_entries(
            cfg,
            root=root_path,
            inputs=inputs,
            callback=callback,
        ):
            results.append((tool_name, action_name, prepared, error))
            if callback:
                event = _FETCH_EVENT_COMPLETED if error is None else _FETCH_EVENT_ERROR
                callback(event, tool_name, action_name, index, total, error)
        return results

    def _build_environment(self, cfg: Config, root: Path | None) -> tuple[ExecutionEnvironment, list[Path]]:
        """Return the execution environment and discovered files for ``cfg``.

        Args:
            cfg: Configuration describing the requested run.
            root: Optional override for the project root.

        Returns:
            tuple[ExecutionEnvironment, list[Path]]: Execution environment and
            the list of matched files.
        """

        root_path = prepare_runtime(root)
        matched_files = discover_files(self._context.discovery, cfg, root_path)
        severity_rules = build_severity_rules(cfg.severity_rules)
        cache_builder = build_cache_context
        if self._services is not None:
            try:
                cache_builder = self._services.resolve("cache_context_builder")
            except ServiceResolutionError:
                cache_builder = build_cache_context
        cache_ctx = cache_builder(cfg, root_path)
        environment = ExecutionEnvironment(
            config=cfg,
            root=root_path,
            severity_rules=severity_rules,
            cache=cache_ctx,
        )
        return environment, matched_files

    def _notify_discovery(self, file_count: int) -> None:
        """Invoke discovery hook when configured.

        Args:
            file_count: Number of files discovered for the run.
        """

        if self._hooks.after_discovery:
            self._hooks.after_discovery(file_count)

    def _notify_plan(self, tool_names: Sequence[str], cfg: Config) -> None:
        """Emit plan statistics via hook when available.

        Args:
            tool_names: Ordered tool names scheduled for execution.
            cfg: Effective configuration used to filter actions.
        """

        if not self._hooks.after_plan:
            return
        total_actions = 0
        for name in tool_names:
            tool = self._context.registry.try_get(name)
            if tool is None:
                continue
            total_actions += sum(1 for action in tool.actions if self._should_run_action(cfg, action))
        self._hooks.after_plan(total_actions)

    def _resolve_annotation_provider(self) -> AnnotationProvider:
        """Return the annotation provider sourced from the service container."""

        try:
            return resolve_annotation_provider(self._services)
        except ServiceResolutionError as error:
            raise ServiceResolutionError("annotation_provider") from error

    def _process_tool(
        self,
        *,
        environment: ExecutionEnvironment,
        tool_name: str,
        matched_files: Sequence[Path],
        state: ExecutionState,
    ) -> bool:
        """Handle execution planning for a single tool.

        Args:
            environment: Execution environment describing the active run.
            tool_name: Name of the tool to process.
            matched_files: Files discovered for the run.
            state: Mutable execution state shared across the run.

        Returns:
            bool: ``True`` when execution should bail early, ``False`` otherwise.
        """

        cfg = environment.config
        tool = self._context.registry.try_get(tool_name)
        if tool is None:
            warn(f"Unknown tool '{tool_name}'", use_emoji=cfg.output.emoji)
            return False

        context = self._build_tool_context(cfg, environment, tool, matched_files)
        self._apply_installers(tool, context, state.installed_tools)
        if self._hooks.before_tool:
            self._hooks.before_tool(tool.name)

        prep_inputs = self._build_preparation_inputs(
            cfg,
            root=environment.root,
            cache_dir=environment.cache.cache_dir,
        )

        for action in tool.actions:
            if not self._should_run_action(cfg, action):
                continue

            preparation = self._prepare_action(
                tool=tool,
                action=action,
                context=context,
                inputs=prep_inputs,
            )
            if preparation.error is not None or preparation.prepared is None:
                raise RuntimeError(preparation.error or "Failed to prepare command")

            prepared_command = preparation.prepared
            invocation = self._build_invocation(tool.name, action, context, prepared_command)
            update_tool_version(environment.cache, tool.name, prepared_command.version)

            cache_decision = self._handle_cached_outcome(
                cfg,
                environment=environment,
                state=state,
                invocation=invocation,
            )
            if cache_decision == _DECISION_BAIL:
                return True
            if cache_decision == _DECISION_SKIP:
                continue

            if self._requires_immediate_execution(cfg, action):
                if self._execute_immediate_action(
                    invocation=invocation,
                    environment=environment,
                    state=state,
                    action=action,
                ):
                    return True
                continue

            self._queue_scheduled_action(state, invocation)
        return False

    def _should_run_action(self, cfg: Config, action: ToolAction) -> bool:
        """Return whether ``action`` should be executed under the current mode."""

        if cfg.execution.fix_only and not action.is_fix:
            return False
        if cfg.execution.check_only and action.is_fix:
            return False
        return True

    def _build_tool_context(
        self,
        cfg: Config,
        environment: ExecutionEnvironment,
        tool: Tool,
        matched_files: Sequence[Path],
    ) -> ToolContext:
        """Return a tool context populated with filtered files and settings.

        Args:
            cfg: Active configuration for the current run.
            environment: Execution environment used to resolve the root path.
            tool: Tool whose context should be constructed.
            matched_files: Files discovered during the discovery phase.

        Returns:
            ToolContext: Context describing the execution environment for ``tool``.
        """

        tool_files = filter_files_for_tool(tool.file_extensions, matched_files)
        settings = MappingProxyType(dict(cfg.tool_settings.get(tool.name, {})))
        return ToolContext(
            cfg=cfg,
            root=environment.root,
            files=tuple(tool_files),
            settings=settings,
        )

    def _build_preparation_inputs(
        self,
        cfg: Config,
        *,
        root: Path,
        cache_dir: Path | None = None,
    ) -> PreparationInputs:
        """Return preparation inputs shared across tool actions.

        Args:
            cfg: Active configuration governing execution behaviour.
            root: Project root path resolved for the current run.
            cache_dir: Directory used to store cached tool outputs.

        Returns:
            PreparationInputs: Immutable view of shared preparation parameters.
        """

        resolved_cache_dir = cache_dir or self._resolve_cache_dir(cfg, root)
        return PreparationInputs(
            root=root,
            cache_dir=resolved_cache_dir,
            system_preferred=not cfg.execution.use_local_linters,
            use_local_override=cfg.execution.use_local_linters,
        )

    def _handle_cached_outcome(
        self,
        cfg: Config,
        *,
        environment: ExecutionEnvironment,
        state: ExecutionState,
        invocation: ActionInvocation,
    ) -> ActionDecision:
        """Attempt to load a cached outcome, returning the resulting decision.

        Args:
            cfg: Active configuration for the current run.
            environment: Execution environment containing cache data.
            state: Mutable execution state shared across actions.
            invocation: Planned action invocation.

        Returns:
            ActionDecision: ``"skip"`` if a cached entry was recorded, ``"bail"``
            if bail mode should halt execution, otherwise ``"execute"``.
        """

        if invocation.internal_runner is not None:
            return _DECISION_EXECUTE

        files: Sequence[Path] = invocation.context.files
        cached_entry = load_cached_outcome(
            environment.cache,
            tool_name=invocation.tool_name,
            action_name=invocation.action.name,
            cmd=invocation.command,
            files=files,
        )
        if cached_entry is None:
            return _DECISION_EXECUTE

        record = OutcomeRecord(
            order=state.order,
            invocation=invocation,
            outcome=cached_entry.outcome,
            file_metrics=cached_entry.file_metrics,
            from_cache=True,
        )
        self._executor.record_outcome(state, environment, record)
        state.order += 1
        if cfg.execution.bail and cached_entry.outcome.returncode != 0:
            state.bail_triggered = True
            return _DECISION_BAIL
        return _DECISION_SKIP

    @staticmethod
    def _requires_immediate_execution(cfg: Config, action: ToolAction) -> bool:
        """Return whether ``action`` should execute synchronously."""

        return action.is_fix or cfg.execution.bail

    def _execute_immediate_action(
        self,
        *,
        invocation: ActionInvocation,
        environment: ExecutionEnvironment,
        state: ExecutionState,
        action: ToolAction,
    ) -> bool:
        """Execute an action immediately, returning ``True`` if bail is triggered.

        Args:
            invocation: Prepared invocation to execute.
            environment: Execution environment describing root and cache.
            state: Mutable execution state to update with outcomes.
            action: Action metadata that informs bail semantics.

        Returns:
            bool: ``True`` when bail mode should halt further execution.
        """

        outcome = self._executor.run_action(invocation, environment)
        record = OutcomeRecord(
            order=state.order,
            invocation=invocation,
            outcome=outcome,
            file_metrics=None,
            from_cache=False,
        )
        self._executor.record_outcome(state, environment, record)
        state.order += 1
        bail_enabled = environment.config.execution.bail
        if bail_enabled and outcome.returncode != 0 and not action.ignore_exit:
            state.bail_triggered = True
            return True
        return False

    def _queue_scheduled_action(self, state: ExecutionState, invocation: ActionInvocation) -> None:
        """Queue ``invocation`` for deferred execution respecting order.

        Args:
            state: Mutable execution state storing the schedule.
            invocation: Invocation ready to be enqueued for later execution.
        """

        state.scheduled.append(ScheduledAction(order=state.order, invocation=invocation))
        state.order += 1

    @staticmethod
    def _resolve_cache_dir(cfg: Config, root: Path) -> Path:
        """Return the cache directory path for ``cfg`` relative to ``root``.

        Args:
            cfg: Configuration providing cache directory settings.
            root: Project root directory used for relative cache paths.

        Returns:
            Path: Absolute cache directory path.
        """

        cache_dir = cfg.execution.cache_dir
        if cache_dir.is_absolute():
            return cache_dir
        return root / cache_dir

    def _build_dry_run_context(self, cfg: Config, root: Path, tool: Tool) -> ToolContext:
        """Return a tool context suitable for preparation without file inputs.

        Args:
            cfg: Active configuration for the current run.
            root: Project root directory resolved for execution.
            tool: Tool whose settings should be exposed via the context.

        Returns:
            ToolContext: Context object with settings and empty file selection.
        """

        settings = MappingProxyType(dict(cfg.tool_settings.get(tool.name, {})))
        return ToolContext(cfg=cfg, root=root, files=tuple(), settings=settings)

    def _iter_fetch_entries(
        self,
        cfg: Config,
        *,
        root: Path,
        inputs: PreparationInputs,
        callback: FetchCallback | None,
    ) -> Iterator[tuple[int, int, str, str, PreparedCommand | None, str | None]]:
        """Yield prepared command information for :meth:`fetch_all_tools`.

        Args:
            cfg: Active configuration for the current run.
            root: Project root directory resolved for execution.
            inputs: Shared preparation inputs for the run.
            callback: Optional callback invoked with progress updates.

        Yields:
            tuple[int, int, str, str, PreparedCommand | None, str | None]: Tuple
            containing the current index, total action count, tool name, action
            name, prepared command, and optional error message.
        """

        actions = self._iter_tool_actions()
        total = len(actions)
        installed_tools: set[str] = set()

        for index, (tool, action) in enumerate(actions, start=1):
            if callback:
                callback(_FETCH_EVENT_START, tool.name, action.name, index, total, None)
            context = self._build_dry_run_context(cfg, root, tool)
            self._apply_installers(tool, context, installed_tools)
            preparation = self._prepare_action(
                tool=tool,
                action=action,
                context=context,
                inputs=inputs,
            )
            yield (
                index,
                total,
                tool.name,
                action.name,
                preparation.prepared,
                preparation.error,
            )

    def _apply_installers(self, tool: Tool, context: ToolContext, installed: set[str]) -> None:
        """Execute tool installers once per run prior to command execution.

        Args:
            tool: Tool whose installers should be executed.
            context: Tool context forwarded to installer callbacks.
            installed: Mutable set tracking previously installed tools.
        """

        if not tool.installers or tool.name in installed:
            return
        for installer in tool.installers:
            installer(context)
        installed.add(tool.name)

    def _invoke_preparer(self, request: CommandPreparationRequest) -> PreparedCommand:
        """Invoke the configured command preparer for ``request``.

        Args:
            request: Normalised command preparation request.

        Returns:
            PreparedCommand: Command ready for execution.
        """

        return self._prepare_command(request)

    def _build_invocation(
        self,
        tool_name: str,
        action: ToolAction,
        context: ToolContext,
        prepared: PreparedCommand,
    ) -> ActionInvocation:
        """Create an :class:`ActionInvocation` from prepared command inputs.

        Args:
            tool_name: Name of the tool being invoked.
            action: Tool action metadata.
            context: Tool context associated with the invocation.
            prepared: Prepared command emitted by the command preparer.

        Returns:
            ActionInvocation: Immutable invocation record consumed by the executor.
        """

        env_overrides = {str(key): str(value) for key, value in prepared.env.items()}
        return ActionInvocation(
            tool_name=tool_name,
            action=action,
            context=context,
            command=tuple(prepared.cmd),
            env_overrides=env_overrides,
            internal_runner=action.internal_runner,
        )

    def _iter_tool_actions(self) -> list[tuple[Tool, ToolAction]]:
        """Return the ordered set of tool/action pairs in the registry.

        Returns:
            list[tuple[Tool, ToolAction]]: Ordered tool/action pairs used for planning.
        """

        ordered_names = self._selector.order_tools([tool.name for tool in self._context.registry.tools()])
        pairs: list[tuple[Tool, ToolAction]] = []
        for name in ordered_names:
            tool = self._context.registry.try_get(name)
            if tool is None:
                continue
            pairs.extend((tool, action) for action in tool.actions)
        return pairs

    def _prepare_action(
        self,
        *,
        tool: Tool,
        action: ToolAction,
        context: ToolContext,
        inputs: PreparationInputs,
    ) -> PreparationResult:
        """Prepare a single tool action for execution.

        Args:
            tool: Tool whose action is being prepared.
            action: Specific tool action to prepare.
            context: Lightweight context used for installer execution.
            inputs: Preparation inputs shared across actions for this run.

        Returns:
            PreparationResult: Description of the preparation outcome.
        """

        if action.internal_runner is not None:
            prepared = PreparedCommand.from_parts(
                cmd=(f"internal::{tool.name}", action.name),
                env={},
                version=None,
                source="project",
            )
            return PreparationResult(tool=tool.name, action=action.name, prepared=prepared, error=None)

        try:
            command = tuple(action.build_command(context))
        except RuntimeError as exc:
            return PreparationResult(tool=tool.name, action=action.name, prepared=None, error=str(exc))

        request = CommandPreparationRequest(
            tool=tool,
            command=command,
            root=inputs.root,
            cache_dir=inputs.cache_dir,
            system_preferred=inputs.system_preferred,
            use_local_override=inputs.use_local_override,
        )
        try:
            prepared = self._invoke_preparer(request)
        except RuntimeError as exc:
            return PreparationResult(tool=tool.name, action=action.name, prepared=None, error=str(exc))
        return PreparationResult(tool=tool.name, action=action.name, prepared=prepared, error=None)

    @staticmethod
    def _resolve_preparer(
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

    @staticmethod
    def _coerce_preparer(
        prepare_callable: Callable[..., PreparedCommand],
    ) -> CommandPreparationFn:
        """Convert ``prepare_callable`` into the modern preparer signature.

        Args:
            prepare_callable: Callable returned by :meth:`_resolve_preparer`.

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
        return Orchestrator._wrap_legacy_preparer(prepare_callable)

    @staticmethod
    def _wrap_legacy_preparer(
        legacy_callable: Callable[..., PreparedCommand],
    ) -> CommandPreparationFn:
        """Wrap legacy preparers that expect discrete arguments.

        Args:
            legacy_callable: Legacy callable expecting discrete parameters.

        Returns:
            CommandPreparationFn: Adapter that builds a request from legacy inputs.
        """

        def _wrapped(request: CommandPreparationRequest) -> PreparedCommand:
            return legacy_callable(
                tool=request.tool,
                base_cmd=list(request.command),
                root=request.root,
                cache_dir=request.cache_dir,
                system_preferred=request.system_preferred,
                use_local_override=request.use_local_override,
            )

        return _wrapped


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


def _build_default_runner() -> RunnerCallable:
    """Return a runner compatible with :class:`ActionExecutor`.

    Returns:
        RunnerCallable: Callable that delegates to :func:`run_command`.
    """

    def _runner(
        cmd: Sequence[str],
        *,
        options: CommandOptions | None = None,
        **overrides: object,
    ) -> CompletedProcess[str]:
        return run_command(cmd, options=options, **overrides)

    return wrap_runner(_runner)


__all__ = [
    "Orchestrator",
    "OrchestratorDeps",
    "OrchestratorHooks",
    "OrchestratorOverrides",
    "CommandPreparationFn",
    "PreparationInputs",
    "PreparationResult",
]
