# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Private mixin containing orchestration helper methods."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from pathlib import Path
from types import MappingProxyType
from collections.abc import Callable

from pyqa.core.environment.tool_env import CommandPreparationRequest, PreparedCommand

from ..cache.context import update_tool_version
from ..config import Config
from ..tools import Tool, ToolAction, ToolContext
from ._pipeline_components import (
    _DECISION_BAIL,
    _DECISION_EXECUTE,
    _DECISION_SKIP,
    _FETCH_EVENT_START,
    ActionDecision,
    FetchCallback,
    PreparationInputs,
    PreparationResult,
    _ActionLoopContext,
    _ActionPlanOutcome,
    _RuntimeContext,
    _ToolingPipeline,
)
from .action_executor import ActionInvocation, ExecutionEnvironment, ExecutionState, OutcomeRecord, ScheduledAction
from .runtime import filter_files_for_tool


class _OrchestratorActionMixin:
    """Helper mixin that encapsulates orchestration workflow helpers."""

    _debug: Callable[[str], None]
    _pipeline: _ToolingPipeline
    _context: _RuntimeContext

    def supports_orchestrator_actions(self) -> bool:
        """Return whether the orchestrator mixin dependencies are present.

        Returns:
            bool: ``True`` when orchestrator state required by the mixin exists.
        """

        return hasattr(self, "_pipeline") and hasattr(self, "_context") and callable(self._debug)

    def orchestrator_action_dependencies(self) -> tuple[str, ...]:
        """Return the private attributes required by the mixin.

        Returns:
            tuple[str, ...]: Attribute names expected on subclasses.
        """

        return ("_pipeline", "_context", "_debug")

    def _handle_tool_action(
        self,
        *,
        action: ToolAction,
        loop_context: _ActionLoopContext,
    ) -> _ActionPlanOutcome:
        """Prepare and schedule or execute ``action`` within ``loop_context``.

        Args:
            action: Action to prepare for execution.
            loop_context: Immutable context describing the active tool, config, and state.

        Returns:
            _ActionPlanOutcome: Outcome describing whether orchestration should continue.
        """

        preparation = self._prepare_action(
            tool=loop_context.tool,
            action=action,
            context=loop_context.tool_context,
            inputs=loop_context.preparation,
        )
        if preparation.error is not None or preparation.prepared is None:
            raise RuntimeError(preparation.error or "Failed to prepare command")

        invocation = self._build_invocation(
            loop_context.tool.name,
            action,
            loop_context.tool_context,
            preparation.prepared,
        )
        command_str = " ".join(invocation.command).replace('"', '\\"')
        self._debug(
            f'prepared {loop_context.tool.name}:{action.name} command="{command_str}" '
            f"internal={invocation.internal_runner is not None}"
        )
        update_tool_version(loop_context.environment.cache, loop_context.tool.name, preparation.prepared.version)

        cache_decision = self._handle_cached_outcome(
            loop_context.cfg,
            environment=loop_context.environment,
            state=loop_context.state,
            invocation=invocation,
        )
        if cache_decision == _DECISION_BAIL:
            self._debug(f"bailing after cached outcome for {loop_context.tool.name}:{action.name}")
            return _ActionPlanOutcome.BAIL
        if cache_decision == _DECISION_SKIP:
            self._debug(f"skipping {loop_context.tool.name}:{action.name} due to cache hit")
            return _ActionPlanOutcome.CONTINUE

        if self._requires_immediate_execution(loop_context.cfg, action):
            self._debug(
                    f"executing {loop_context.tool.name}:{action.name} immediately "
                    f"(is_fix={action.is_fix}, bail={loop_context.cfg.execution.bail})"
            )
            should_bail = self._execute_immediate_action(
                invocation=invocation,
                environment=loop_context.environment,
                state=loop_context.state,
                action=action,
            )
            return _ActionPlanOutcome.BAIL if should_bail else _ActionPlanOutcome.CONTINUE

        self._queue_scheduled_action(loop_context.state, invocation)
        queued_cmd = " ".join(invocation.command).replace('"', '\\"')
        self._debug(f'queued {loop_context.tool.name}:{action.name} command="{queued_cmd}"')
        return _ActionPlanOutcome.CONTINUE

    def _format_skip_reason(self, tool_name: str, action: ToolAction, cfg: Config) -> str:
        """Return a formatted skip reason for debug logging.

        Args:
            tool_name: Display name of the tool.
            action: Action that has been skipped.
            cfg: Configuration supplying execution flags.

        Returns:
            str: Human readable skip message.
        """

        reasons: list[str] = []
        if cfg.execution.fix_only and not action.is_fix:
            reasons.append("fix_only active")
        if cfg.execution.check_only and action.is_fix:
            reasons.append("check_only active")
        reason_text = ", ".join(reasons) or "action filtered"
        return f"skipping {tool_name}:{action.name} ({reason_text})"

    def _should_run_action(self, cfg: Config, action: ToolAction) -> bool:
        """Return whether ``action`` should be executed under the current mode.

        Args:
            cfg: Configuration providing execution flags such as ``fix_only``.
            action: Tool action evaluated for execution eligibility.

        Returns:
            bool: ``True`` when the action should run, ``False`` otherwise.
        """

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
        cached_entry = environment.cache.load_cached_outcome(
            tool_name=invocation.tool_name,
            action_name=invocation.action.name,
            cmd=invocation.command,
            files=files,
        )
        if cached_entry is None:
            self._debug(f"no cache entry for {invocation.tool_name}:{invocation.action.name}")
            return _DECISION_EXECUTE

        record = OutcomeRecord(
            order=state.order,
            invocation=invocation,
            outcome=cached_entry.outcome,
            file_metrics=cached_entry.file_metrics,
            from_cache=True,
        )
        self._pipeline.executor.record_outcome(state, environment, record)
        state.order += 1
        if cfg.execution.bail and cached_entry.outcome.returncode != 0:
            state.bail_triggered = True
            self._debug(
                f"cached failure triggers bail for {invocation.tool_name}:{invocation.action.name} "
                f"returncode={cached_entry.outcome.returncode}"
            )
            return _DECISION_BAIL
        self._debug(
            f"cache hit for {invocation.tool_name}:{invocation.action.name} "
            f"returncode={cached_entry.outcome.returncode}"
        )
        return _DECISION_SKIP

    @staticmethod
    def _requires_immediate_execution(cfg: Config, action: ToolAction) -> bool:
        """Return whether ``action`` should execute synchronously.

        Args:
            cfg: Configuration providing execution hints such as ``bail``.
            action: Tool action evaluated for immediate execution.

        Returns:
            bool: ``True`` when the action should execute immediately.
        """

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

        outcome = self._pipeline.executor.run_action(invocation, environment)
        record = OutcomeRecord(
            order=state.order,
            invocation=invocation,
            outcome=outcome,
            file_metrics=None,
            from_cache=False,
        )
        self._pipeline.executor.record_outcome(state, environment, record)
        state.order += 1
        bail_enabled = environment.config.execution.bail
        if bail_enabled and outcome.returncode != 0 and not action.ignore_exit:
            state.bail_triggered = True
            failure_message = (
                f"{invocation.tool_name}:{invocation.action.name} immediate execution failed "
                f"with returncode={outcome.returncode}; bail active"
            )
            self._debug(failure_message)
            return True
        completion_message = (
            f"completed {invocation.tool_name}:{invocation.action.name} immediate execution "
            f"returncode={outcome.returncode} diagnostics={len(outcome.diagnostics)}"
        )
        self._debug(completion_message)
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
            self._debug(f"running installer for {tool.name}")
            installer(context)
        installed.add(tool.name)
        self._debug(f"completed installers for {tool.name}")

    def _invoke_preparer(self, request: CommandPreparationRequest) -> PreparedCommand:
        """Invoke the configured command preparer for ``request``.

        Args:
            request: Normalised command preparation request.

        Returns:
            PreparedCommand: Command ready for execution.
        """

        return self._pipeline.prepare_command(request)

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

        ordered_names = self._pipeline.selector.order_tools([tool.name for tool in self._context.registry.tools()])
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
