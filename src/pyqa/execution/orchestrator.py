# SPDX-License-Identifier: MIT
"""High level orchestration for running registered lint tools."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from subprocess import CompletedProcess
from types import MappingProxyType
from typing import Final, Literal

from ..analysis import apply_change_impact, apply_suppression_hints, build_refactor_navigator
from ..annotations import AnnotationEngine
from ..config import Config
from ..diagnostics import build_severity_rules, dedupe_outcomes
from ..discovery.base import SupportsDiscovery
from ..logging import warn
from ..models import RunResult, ToolOutcome
from ..tool_env import CommandPreparationRequest, CommandPreparer, PreparedCommand
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
)
from .cache_context import build_cache_context, load_cached_outcome, save_versions, update_tool_version
from .runtime import discover_files, filter_files_for_tool, prepare_runtime
from .tool_selection import ToolSelector
from .worker import run_command

FetchEvent = Literal["start", "completed", "error"]

_ANALYSIS_ENGINE: Final[AnnotationEngine] = AnnotationEngine()
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


class Orchestrator:
    """Coordinates discovery, tool selection, and execution."""

    def __init__(
        self,
        deps: OrchestratorDeps | None = None,
        *,
        registry: ToolRegistry | None = None,
        discovery: SupportsDiscovery | None = None,
        runner: RunnerCallable | None = None,
        hooks: OrchestratorHooks | None = None,
        cmd_preparer: CommandPreparationFn | None = None,
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

        if deps is not None:
            if any(value is not None for value in (registry, discovery, runner, hooks, cmd_preparer)):
                raise TypeError("Pass either 'deps' or explicit keyword arguments, not both")
            registry = deps.registry
            discovery = deps.discovery
            runner = deps.runner or runner
            hooks = deps.hooks or hooks
            cmd_preparer = deps.cmd_preparer or cmd_preparer
        if registry is None or discovery is None:
            raise TypeError("Orchestrator requires 'registry' and 'discovery' dependencies")

        self._registry = registry
        self._discovery = discovery
        self._runner = runner or _build_default_runner()
        self._hooks = hooks or OrchestratorHooks()
        preparer = cmd_preparer
        if preparer is None:
            default_preparer = CommandPreparer()
            preparer = default_preparer.prepare_request
        if hasattr(preparer, "prepare") and callable(getattr(preparer, "prepare")):
            prepare_callable = getattr(preparer, "prepare")
        elif callable(preparer):
            prepare_callable = preparer
        else:
            raise TypeError("cmd_preparer must be callable or expose a callable 'prepare' attribute")
        self._prepare_command: CommandPreparationFn = prepare_callable
        self._selector = ToolSelector(self._registry)
        self._executor = ActionExecutor(self._runner, self._hooks.after_tool)

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
        dedupe_outcomes(result, cfg.dedupe)
        _ANALYSIS_ENGINE.annotate_run(result)
        apply_suppression_hints(result, _ANALYSIS_ENGINE)
        apply_change_impact(result)
        build_refactor_navigator(result, _ANALYSIS_ENGINE)
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
        cache_dir = (
            cfg.execution.cache_dir if cfg.execution.cache_dir.is_absolute() else root_path / cfg.execution.cache_dir
        )
        inputs = PreparationInputs(
            root=root_path,
            cache_dir=cache_dir,
            system_preferred=not cfg.execution.use_local_linters,
            use_local_override=cfg.execution.use_local_linters,
        )
        results: list[tuple[str, str, PreparedCommand | None, str | None]] = []

        actions = self._iter_tool_actions()
        total = len(actions)
        installed_tools: set[str] = set()

        for index, (tool, action) in enumerate(actions, start=1):
            if callback:
                callback("start", tool.name, action.name, index, total, None)
            settings_view = MappingProxyType(dict(cfg.tool_settings.get(tool.name, {})))
            context = ToolContext(cfg=cfg, root=root_path, files=tuple(), settings=settings_view)
            self._apply_installers(tool, context, installed_tools)
            preparation = self._prepare_action(
                tool=tool,
                action=action,
                context=context,
                inputs=inputs,
            )
            results.append((tool.name, action.name, preparation.prepared, preparation.error))
            if callback:
                event = "completed" if preparation.error is None else "error"
                callback(event, tool.name, action.name, index, total, preparation.error)
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
        matched_files = discover_files(self._discovery, cfg, root_path)
        severity_rules = build_severity_rules(cfg.severity_rules)
        cache_ctx = build_cache_context(cfg, root_path)
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
            tool = self._registry.try_get(name)
            if tool is None:
                continue
            total_actions += sum(1 for action in tool.actions if self._should_run_action(cfg, action))
        self._hooks.after_plan(total_actions)

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

        tool = self._registry.try_get(tool_name)
        cfg = environment.config
        if tool is None:
            warn(f"Unknown tool '{tool_name}'", use_emoji=cfg.output.emoji)
            return False
        tool_files = filter_files_for_tool(tool.file_extensions, matched_files)
        settings_view = MappingProxyType(dict(cfg.tool_settings.get(tool.name, {})))
        context = ToolContext(cfg=cfg, root=environment.root, files=tuple(tool_files), settings=settings_view)
        self._apply_installers(tool, context, state.installed_tools)
        if self._hooks.before_tool:
            self._hooks.before_tool(tool.name)

        for action in tool.actions:
            if not self._should_run_action(cfg, action):
                continue
            request = CommandPreparationRequest(
                tool=tool,
                command=tuple(action.build_command(context)),
                root=environment.root,
                cache_dir=environment.cache.cache_dir,
                system_preferred=not cfg.execution.use_local_linters,
                use_local_override=cfg.execution.use_local_linters,
            )
            prepared = self._invoke_preparer(request)
            invocation = self._build_invocation(tool.name, action, context, prepared)
            update_tool_version(environment.cache, tool.name, prepared.version)
            cached_entry = load_cached_outcome(
                environment.cache,
                tool_name=tool.name,
                action_name=action.name,
                cmd=invocation.command,
                files=context.files,
            )
            if cached_entry is not None:
                record = OutcomeRecord(
                    order=state.order,
                    invocation=invocation,
                    outcome=cached_entry.outcome,
                    file_metrics=cached_entry.file_metrics,
                    from_cache=True,
                )
                self._executor.record_outcome(state, environment, record)
                if cfg.execution.bail and cached_entry.outcome.returncode != 0:
                    state.bail_triggered = True
                    return True
                state.order += 1
                continue

            if action.is_fix or cfg.execution.bail:
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
                if cfg.execution.bail and outcome.returncode != 0 and not action.ignore_exit:
                    state.bail_triggered = True
                    return True
                continue

            state.scheduled.append(ScheduledAction(order=state.order, invocation=invocation))
            state.order += 1
        return False

    def _should_run_action(self, cfg: Config, action: ToolAction) -> bool:
        """Return whether ``action`` should be executed under the current mode."""

        if cfg.execution.fix_only and not action.is_fix:
            return False
        if cfg.execution.check_only and action.is_fix:
            return False
        return True

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

        try:
            return self._prepare_command(request)
        except TypeError as exc:
            try:
                return self._prepare_command(  # type: ignore[misc]
                    tool=request.tool,
                    base_cmd=list(request.command),
                    root=request.root,
                    cache_dir=request.cache_dir,
                    system_preferred=request.system_preferred,
                    use_local_override=request.use_local_override,
                )
            except TypeError:
                raise exc

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
        )

    def _iter_tool_actions(self) -> list[tuple[Tool, ToolAction]]:
        """Return the ordered set of tool/action pairs in the registry.

        Returns:
            list[tuple[Tool, ToolAction]]: Ordered tool/action pairs used for planning.
        """

        ordered_names = self._selector.order_tools([tool.name for tool in self._registry.tools()])
        pairs: list[tuple[Tool, ToolAction]] = []
        for name in ordered_names:
            tool = self._registry.try_get(name)
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

        try:
            request = CommandPreparationRequest(
                tool=tool,
                command=tuple(action.build_command(context)),
                root=inputs.root,
                cache_dir=inputs.cache_dir,
                system_preferred=inputs.system_preferred,
                use_local_override=inputs.use_local_override,
            )
            prepared = self._invoke_preparer(request)
            return PreparationResult(tool=tool.name, action=action.name, prepared=prepared, error=None)
        except RuntimeError as exc:
            return PreparationResult(tool=tool.name, action=action.name, prepared=None, error=str(exc))


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
        cwd: Path | None = None,
        env: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> CompletedProcess[str]:
        return run_command(cmd, cwd=cwd, env=env, timeout=timeout)

    return _runner


__all__ = [
    "Orchestrator",
    "OrchestratorDeps",
    "OrchestratorHooks",
    "CommandPreparationFn",
    "PreparationInputs",
    "PreparationResult",
]
