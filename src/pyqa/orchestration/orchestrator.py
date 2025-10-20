# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""High level orchestration for running registered lint tools."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from pyqa.core.environment.tool_env import CommandPreparer, PreparedCommand

from ..analysis.bootstrap import register_analysis_services
from ..analysis.change_impact import apply_change_impact
from ..analysis.navigator import build_refactor_navigator
from ..analysis.services import (
    resolve_annotation_provider,
    resolve_context_resolver,
    resolve_function_scale_estimator,
)
from ..analysis.suppression import apply_suppression_hints
from ..cache.context import CacheContext, build_cache_context
from ..config import Config
from ..core.logging import warn
from ..core.models import RunResult
from ..core.runtime import ServiceContainer, ServiceResolutionError, register_default_services
from ..diagnostics import build_severity_rules, dedupe_outcomes
from ..discovery.base import SupportsDiscovery
from ..interfaces.orchestration import OrchestratorHooks
from ..interfaces.runtime import ServiceRegistryProtocol
from ..tools.registry import ToolRegistry
from ._orchestrator_mixins import _OrchestratorActionMixin
from ._pipeline_components import (
    _FETCH_EVENT_COMPLETED,
    _FETCH_EVENT_ERROR,
    _TOOL_DECISION_SKIP,
    CommandPreparationFn,
    FetchEvent,
    PreparationInputs,
    PreparationResult,
    _ActionLoopContext,
    _ActionPlanOutcome,
    _AnalysisProviders,
    _RuntimeContext,
    _ToolingPipeline,
    build_default_runner,
    coerce_preparer,
    resolve_preparer,
)
from .action_executor import (
    ActionExecutor,
    ExecutionEnvironment,
    ExecutionState,
    RunnerCallable,
)
from .runtime import discover_files, prepare_runtime
from .tool_selection import SelectionResult, ToolDecision, ToolSelector

FetchCallback = Callable[[FetchEvent, str, str, int, int, str | None], None]


def _resolve_cache_builder(services: ServiceRegistryProtocol | None) -> Callable[[Config, Path], CacheContext]:
    """Return the cache context builder available from ``services``.

    Args:
        services: Optional service registry supplied to the orchestrator.

    Returns:
        Callable[[Config, Path], CacheContext]: Cache builder callable capable of
            initialising cache state for orchestrator actions.
    """

    if services is None:
        return build_cache_context
    try:
        builder_candidate = services.resolve("cache_context_builder")
    except ServiceResolutionError:
        return build_cache_context
    if not callable(builder_candidate):
        return build_cache_context
    return cast(Callable[[Config, Path], CacheContext], builder_candidate)


@dataclass(frozen=True)
class OrchestratorDeps:
    """Dependencies required to construct an :class:`Orchestrator`."""

    registry: ToolRegistry
    discovery: SupportsDiscovery
    runner: RunnerCallable | None = None
    hooks: OrchestratorHooks | None = None
    cmd_preparer: CommandPreparationFn | None = None
    services: ServiceRegistryProtocol | None = None
    debug_logger: Callable[[str], None] | None = None


@dataclass(frozen=True)
class OrchestratorOverrides:
    """Optional overrides applied when constructing an :class:`Orchestrator`."""

    runner: RunnerCallable | None = None
    hooks: OrchestratorHooks | None = None
    cmd_preparer: CommandPreparationFn | None = None
    services: ServiceRegistryProtocol | None = None
    debug_logger: Callable[[str], None] | None = None


class Orchestrator(_OrchestratorActionMixin):
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
                    overrides.debug_logger,
                )
            ):
                raise TypeError("Pass either 'deps' or explicit overrides, not both")
            registry = deps.registry
            discovery = deps.discovery
            final_runner = deps.runner or overrides.runner
            final_hooks = deps.hooks or overrides.hooks
            final_preparer = deps.cmd_preparer or overrides.cmd_preparer
            services = deps.services
            debug_logger = overrides.debug_logger or deps.debug_logger
        else:
            final_runner = overrides.runner
            final_hooks = overrides.hooks
            final_preparer = overrides.cmd_preparer
            services = overrides.services
            debug_logger = overrides.debug_logger
        if registry is None or discovery is None:
            raise TypeError("Orchestrator requires 'registry' and 'discovery' dependencies")

        self._context = _RuntimeContext(registry=registry, discovery=discovery)
        base_runner = final_runner or build_default_runner()
        self._runner = base_runner if isinstance(base_runner, RunnerCallable) else wrap_runner(base_runner)
        self._hooks = final_hooks or OrchestratorHooks()
        self._services: ServiceRegistryProtocol = services or ServiceContainer()
        self._ensure_bootstrap_services()
        self._debug_logger: Callable[[str], None] | None = debug_logger
        self._analysis = self._create_analysis_providers()
        self._pipeline = self._create_pipeline(final_preparer)

    def _debug(self, message: str) -> None:
        """Emit ``message`` to the configured debug logger when available.

        Args:
            message: Textual content describing the orchestration step.
        """

        if self._debug_logger:
            self._debug_logger(message)

    def _ensure_bootstrap_services(self) -> None:
        """Ensure core analysis/default services exist on the container."""

        register_default_services(self._services)
        register_analysis_services(self._services)

    def _create_pipeline(
        self,
        preparer_override: CommandPreparer | CommandPreparationFn | Callable[..., PreparedCommand] | None,
    ) -> _ToolingPipeline:
        """Return a tooling pipeline configured with preparer and executor.

        Args:
            preparer_override: Optional callable supplied by the caller.

        Returns:
            _ToolingPipeline encapsulating selection, preparation, and execution.
        """

        preparer: CommandPreparationFn | Callable[..., PreparedCommand] | CommandPreparer | None = preparer_override
        if preparer is None:
            default_preparer = CommandPreparer()
            preparer = default_preparer.prepare_request
        prepare_callable = resolve_preparer(preparer)
        prepare_fn = coerce_preparer(prepare_callable)
        selector = ToolSelector(self._context.registry)
        executor = ActionExecutor(
            runner=self._runner,
            after_tool_hook=self._hooks.after_tool,
            context_resolver=self._analysis.context_resolver,
            debug_logger=self._debug_logger,
        )
        return _ToolingPipeline(selector=selector, executor=executor, prepare_command=prepare_fn)

    def _create_analysis_providers(self) -> _AnalysisProviders:
        """Return annotation and analysis providers for the orchestrator.

        Returns:
            _AnalysisProviders: Aggregated provider bundle used by the pipeline.
        """

        annotation_provider = self._resolve_annotation_provider()
        function_scale = resolve_function_scale_estimator(self._services)
        context_resolver = resolve_context_resolver(self._services)
        return _AnalysisProviders(
            annotation=annotation_provider,
            function_scale=function_scale,
            context_resolver=context_resolver,
        )

    @property
    def _annotation_provider(self) -> AnnotationProvider:
        """Expose the active annotation provider for legacy integrations.

        Returns:
            AnnotationProvider: Annotation provider active for the orchestrator.
        """

        return self._analysis.annotation

    def run(self, cfg: Config, *, root: Path | None = None) -> RunResult:
        """Execute configured tools and aggregate their outcomes.

        Args:
            cfg: Configuration describing the requested run.
            root: Optional override for the project root directory.

        Returns:
            RunResult: Aggregated results, outcomes, and metadata for the run.
        """

        environment, matched_files = self._build_environment(cfg, root)
        state = ExecutionState()
        self._pipeline.executor.after_tool_hook = self._hooks.after_tool
        self._debug(f"execution root={environment.root} matched_files={len(matched_files)}")
        self._notify_discovery(len(matched_files))

        selection = self._plan_from_environment(cfg, environment, matched_files)
        tool_names = list(selection.run_names)
        self._notify_plan(tool_names, cfg)

        for name in tool_names:
            if self._process_tool(
                environment=environment,
                tool_name=name,
                matched_files=matched_files,
                state=state,
            ):
                break

        self._pipeline.executor.execute_scheduled(environment, state)
        outcomes = [state.outcomes[index] for index in sorted(state.outcomes)]
        self._pipeline.executor.populate_missing_metrics(state, matched_files)
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
            annotation_provider=self._analysis.annotation,
        )
        self._analysis.annotation.annotate_run(result)
        apply_suppression_hints(result, self._analysis.annotation)
        apply_change_impact(result, context_resolver=self._analysis.context_resolver)
        build_refactor_navigator(
            result,
            self._analysis.annotation,
            function_scale=self._analysis.function_scale,
        )
        environment.cache.persist_versions()
        if self._hooks.after_execution:
            self._hooks.after_execution(result)
        return result

    def plan_tools(
        self,
        cfg: Config,
        *,
        root: Path | None = None,
    ) -> SelectionResult:
        """Return the tool selection result without executing actions.

        Args:
            cfg: Configuration describing the requested run.
            root: Optional override for the project root directory.

        Returns:
            SelectionResult: Planned selection of tools and actions.
        """

        environment, matched_files = self._build_environment(cfg, root)
        self._debug(f"execution root={environment.root} matched_files={len(matched_files)}")
        return self._plan_from_environment(cfg, environment, matched_files)

    def fetch_all_tools(
        self,
        cfg: Config,
        *,
        root: Path | None = None,
        callback: FetchCallback | None = None,
    ) -> list[tuple[str, str, PreparedCommand | None, str | None]]:
        """Prepared command metadata for all tools without executing them.

        Args:
            cfg: Configuration describing the requested run.
            root: Optional override for the project root directory.
            callback: Optional callback invoked with fetch progress events.

        Returns:
            list[tuple[str, str, PreparedCommand | None, str | None]]: Collection
            describing the prepared commands and any associated error text.
        """

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
        cache_builder = _resolve_cache_builder(self._services)
        cache_ctx = cache_builder(cfg, root_path)
        environment = ExecutionEnvironment(
            config=cfg,
            root=root_path,
            severity_rules=severity_rules,
            cache=cache_ctx,
        )
        return environment, matched_files

    def _plan_from_environment(
        self,
        cfg: Config,
        environment: ExecutionEnvironment,
        matched_files: Sequence[Path],
    ) -> SelectionResult:
        """Return the selection plan derived from the discovery environment.

        Args:
            cfg: Configuration used to evaluate tool eligibility.
            environment: Execution environment capturing cache and severity data.
            matched_files: Files gathered during the discovery stage.

        Returns:
            SelectionResult: Plan describing actions to execute or skip.
        """

        selection = self._pipeline.selector.plan_selection(cfg, matched_files, environment.root)
        self._debug_selection(selection, cfg)
        return selection

    def _debug_selection(self, selection: SelectionResult, cfg: Config) -> None:
        """Emit debug information for tool decisions when debugging is enabled.

        Args:
            selection: Planned selection returned by the selector.
            cfg: Configuration providing filtering and CLI inputs.
        """

        if not self._debug_logger:
            return
        run_names = list(selection.run_names)
        self._debug(f"selected tools: {run_names}")
        skipped = [
            decision.name
            for decision in selection.decisions
            if decision.action == _TOOL_DECISION_SKIP and decision.eligibility.available
        ]
        if skipped:
            self._debug(f"skipped tools: {skipped} -- only={cfg.execution.only} languages={cfg.execution.languages}")
        for decision in selection.decisions:
            self._debug(self._format_decision_debug(decision))

    def _format_decision_debug(self, decision: ToolDecision) -> str:
        """Return a formatted string describing a tool selection decision.

        Args:
            decision: Individual decision returned by the selector.

        Returns:
            str: Human readable description summarising decision metadata.
        """

        parts: list[str] = [
            "[plan]",
            f"tool={decision.name}",
            f"action={decision.action}",
            f"family={decision.family}",
        ]
        reasons = ",".join(decision.reasons)
        parts.append(f'reasons="{reasons}"')
        elig = decision.eligibility
        if elig.requested_via_only:
            parts.append("requested=only")
        if elig.language_match is not None:
            parts.append(f"lang={elig.language_match}")
        if elig.extension_match is not None:
            parts.append(f"ext={elig.extension_match}")
        if elig.config_match is not None:
            parts.append(f"config={elig.config_match}")
        if elig.sensitivity_ok is not None:
            parts.append(f"sensitivity={elig.sensitivity_ok}")
        if elig.pyqa_scope is not None:
            parts.append(f"pyqa={elig.pyqa_scope}")
        if elig.default_enabled:
            parts.append("default_enabled=True")
        if not elig.available:
            parts.append("available=False")
        return " ".join(parts)

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
        """Return the annotation provider sourced from the service container.

        Returns:
            AnnotationProvider: Annotation provider resolved from the container.

        Raises:
            ServiceResolutionError: If annotation services are unavailable.
        """

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
            self._debug(f"skipping unknown tool '{tool_name}'")
            return False

        context = self._build_tool_context(cfg, environment, tool, matched_files)
        settings_snapshot = dict(context.settings)
        self._debug(
            f"tool {tool.name}: files={len(context.files)} "
            f"fix_only={cfg.execution.fix_only} check_only={cfg.execution.check_only} "
            f"settings={settings_snapshot}"
        )
        self._apply_installers(tool, context, state.installed_tools)
        if self._hooks.before_tool:
            self._hooks.before_tool(tool.name)

        prep_inputs = self._build_preparation_inputs(
            cfg,
            root=environment.root,
            cache_dir=environment.cache.cache_dir,
        )

        loop_context = _ActionLoopContext(
            cfg=cfg,
            environment=environment,
            state=state,
            tool=tool,
            tool_context=context,
            preparation=prep_inputs,
        )

        for action in tool.actions:
            should_run = self._should_run_action(cfg, action)
            if not should_run:
                self._debug(self._format_skip_reason(loop_context.tool.name, action, loop_context.cfg))
                continue

            outcome = self._handle_tool_action(action=action, loop_context=loop_context)
            if outcome is _ActionPlanOutcome.BAIL:
                return True
        return False


__all__ = [
    "Orchestrator",
    "OrchestratorDeps",
    "OrchestratorHooks",
    "OrchestratorOverrides",
    "CommandPreparationFn",
    "PreparationInputs",
    "PreparationResult",
]
