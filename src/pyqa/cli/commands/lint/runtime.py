# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Runtime data structures and factories shared across lint CLI helpers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import cast

from pyqa.interfaces.config import Config as ConfigProtocol
from pyqa.interfaces.linting import PreparedLintState as PreparedLintStateView

from ....analysis.bootstrap import register_analysis_services
from ....catalog.model_catalog import CatalogSnapshot
from ....core.environment.tool_env.models import PreparedCommand
from ....core.models import RunResult, ToolOutcome
from ....discovery import build_default_discovery
from ....discovery.base import SupportsDiscovery
from ....interfaces.orchestration import ExecutionPipeline, OrchestratorHooks
from ....interfaces.orchestration_selection import SelectionResult
from ....interfaces.runtime import ServiceRegistryProtocol
from ....linting.registry import configure_internal_tool_defaults, ensure_internal_tools_registered
from ....orchestration.orchestrator import (
    FetchCallback,
    Orchestrator,
)
from ....orchestration.orchestrator import OrchestratorHooks as ConcreteOrchestratorHooks
from ....orchestration.orchestrator import (
    OrchestratorOverrides,
)
from ....tools.builtin_registry import initialize_registry
from ....tools.registry import DEFAULT_REGISTRY, ToolRegistry
from ...core.runtime import ServiceContainer, ServiceResolutionError, register_default_services


@dataclass(slots=True)
class LintRuntimeContext:
    """Bundle runtime dependencies for lint execution."""

    state: PreparedLintStateView
    config: ConfigProtocol
    registry: ToolRegistry
    orchestrator: ExecutionPipeline
    hooks: OrchestratorHooks
    catalog_snapshot: CatalogSnapshot
    services: ServiceRegistryProtocol | None = None
    plugins: SimpleNamespace | None = None


@dataclass(slots=True)
class LintRuntimeDependencies:
    """Collaborators required to construct :class:`LintRuntimeContext`."""

    registry: ToolRegistry
    discovery_factory: Callable[[], SupportsDiscovery]
    orchestrator_factory: Callable[
        [ToolRegistry, SupportsDiscovery, OrchestratorHooks, Callable[[str], None] | None],
        ExecutionPipeline,
    ]
    catalog_initializer: Callable[[ToolRegistry], CatalogSnapshot]
    services: ServiceRegistryProtocol | None = None


def _default_orchestrator_factory(
    registry: ToolRegistry,
    discovery: SupportsDiscovery,
    hooks: OrchestratorHooks,
    *,
    services: ServiceRegistryProtocol | None = None,
    debug_logger: Callable[[str], None] | None = None,
) -> ExecutionPipeline:
    """Return an execution pipeline backed by the default orchestrator.

    Args:
        registry: Tool registry providing available tool implementations.
        discovery: Discovery strategy responsible for enumerating project files.
        hooks: Hook bundle receiving orchestrator lifecycle callbacks.
        services: Optional service registry supplying runtime collaborators.
        debug_logger: Optional logger invoked with debug diagnostics.

    Returns:
        Pipeline that drives tool planning and execution.
    """

    overrides = OrchestratorOverrides(
        hooks=_coerce_hooks(hooks),
        services=services,
        debug_logger=debug_logger,
    )
    orchestrator = Orchestrator(registry=registry, discovery=discovery, overrides=overrides)
    return _OrchestratorExecutionPipeline(orchestrator)


def _coerce_hooks(hooks: OrchestratorHooks) -> ConcreteOrchestratorHooks:
    """Return a concrete orchestrator hooks instance that proxies callbacks.

    Args:
        hooks: Hook bundle supplied by the CLI layer.

    Returns:
        Hook adapter forwarding invocations safely.
    """

    concrete = ConcreteOrchestratorHooks()

    concrete.before_tool = _BeforeToolProxy(hooks).run
    concrete.after_tool = _AfterToolProxy(hooks).run
    concrete.after_discovery = _AfterDiscoveryProxy(hooks).run
    concrete.after_execution = _AfterExecutionProxy(hooks).run
    concrete.after_plan = _AfterPlanProxy(hooks).run
    return concrete


@dataclass(slots=True)
class _BeforeToolProxy:
    """Proxy that safely invokes the ``before_tool`` hook."""

    hooks: OrchestratorHooks

    def run(self, tool_name: str) -> None:
        """Invoke ``before_tool`` when defined.

        Args:
            tool_name: Identifier of the tool scheduled for execution.
        """

        callback = self.hooks.before_tool
        if callback is not None:
            callback(tool_name)


@dataclass(slots=True)
class _AfterToolProxy:
    """Proxy that invokes the ``after_tool`` hook on completion."""

    hooks: OrchestratorHooks

    def run(self, outcome: ToolOutcome) -> None:
        """Invoke ``after_tool`` when defined.

        Args:
            outcome: Tool outcome generated after execution.
        """

        callback = self.hooks.after_tool
        if callback is not None:
            callback(outcome)


@dataclass(slots=True)
class _AfterDiscoveryProxy:
    """Proxy that invokes ``after_discovery`` following project scan."""

    hooks: OrchestratorHooks

    def run(self, file_count: int) -> None:
        """Invoke ``after_discovery`` when defined.

        Args:
            file_count: Number of files discovered for analysis.
        """

        callback = self.hooks.after_discovery
        if callback is not None:
            callback(file_count)


@dataclass(slots=True)
class _AfterExecutionProxy:
    """Proxy that invokes the ``after_execution`` hook."""

    hooks: OrchestratorHooks

    def run(self, result: RunResult) -> None:
        """Invoke ``after_execution`` when defined.

        Args:
            result: Aggregated run result emitted after orchestrator completion.
        """

        callback = self.hooks.after_execution
        if callback is not None:
            callback(result)


@dataclass(slots=True)
class _AfterPlanProxy:
    """Proxy that invokes ``after_plan`` when selection completes."""

    hooks: OrchestratorHooks

    def run(self, planned_tools: int) -> None:
        """Invoke ``after_plan`` when defined.

        Args:
            planned_tools: Number of tools scheduled for execution.
        """

        callback = self.hooks.after_plan
        if callback is not None:
            callback(planned_tools)


class _OrchestratorExecutionPipeline(ExecutionPipeline):
    """Execution pipeline backed by the core orchestrator implementation."""

    def __init__(self, orchestrator: Orchestrator) -> None:
        """Initialise the execution pipeline.

        Args:
            orchestrator: Underlying orchestrator coordinating tool execution.
        """

        self._orchestrator = orchestrator

    @property
    def pipeline_name(self) -> str:
        """Return the descriptive pipeline name.

        Returns:
            Human-readable identifier for the pipeline.
        """

        return "orchestrator"

    def run(self, config: ConfigProtocol, *, root: Path) -> RunResult:
        """Execute the orchestrator for ``config`` rooted at ``root``.

        Args:
            config: Lint configuration controlling selection and execution.
            root: Project root directory used for tool invocations.

        Returns:
            Aggregated run result generated by the orchestrator.
        """

        return self._orchestrator.run(config, root=root)

    def fetch_all_tools(
        self,
        config: ConfigProtocol,
        *,
        root: Path,
        callback: FetchCallback | None = None,
    ) -> list[tuple[str, str, PreparedCommand | None, str | None]]:
        """Prepare tool executions without running them.

        Args:
            config: Lint configuration controlling tool selection.
            root: Project root directory used for tool resolution.
            callback: Optional hook invoked for each fetch event.

        Returns:
            Collection describing prepared tool actions, associated commands, and error messages.
        """

        return self._orchestrator.fetch_all_tools(config, root=root, callback=callback)

    def plan_tools(self, config: ConfigProtocol, *, root: Path) -> SelectionResult:
        """Return the orchestrator plan without executing actions.

        Args:
            config: Lint configuration steering tool selection.
            root: Project root directory used to contextualise analysis.

        Returns:
            Planning metadata enumerating planned tool actions ready for execution.
        """

        return self._orchestrator.plan_tools(config, root=root)


_DEFAULT_SERVICES = ServiceContainer()
register_default_services(_DEFAULT_SERVICES)
register_analysis_services(_DEFAULT_SERVICES)


def _orchestrator_with_default_services(
    registry: ToolRegistry,
    discovery: SupportsDiscovery,
    hooks: OrchestratorHooks,
    debug_logger: Callable[[str], None] | None = None,
) -> ExecutionPipeline:
    """Return an orchestrator wired with the shared default services.

    Args:
        registry: Tool registry providing available tool implementations.
        discovery: Discovery strategy used to enumerate project files.
        hooks: Hook bundle provided by CLI dependencies.
        debug_logger: Optional logger receiving debug diagnostics.

    Returns:
        Pipeline configured with default runtime services.
    """

    return _default_orchestrator_factory(
        registry,
        discovery,
        hooks,
        services=_DEFAULT_SERVICES,
        debug_logger=debug_logger,
    )


DEFAULT_LINT_DEPENDENCIES = LintRuntimeDependencies(
    registry=DEFAULT_REGISTRY,
    discovery_factory=build_default_discovery,
    orchestrator_factory=_orchestrator_with_default_services,
    catalog_initializer=lambda registry: initialize_registry(registry=registry),
    services=_DEFAULT_SERVICES,
)


def _resolve_plugin_namespace(services: ServiceRegistryProtocol | None) -> SimpleNamespace | None:
    """Return the plugin namespace resolved from ``services`` when available.

    Args:
        services: Optional service registry providing resolution helpers.

    Returns:
        SimpleNamespace | None: Loaded plugin namespace when resolvable; otherwise ``None``.
    """

    if services is None:
        return None
    try:
        plugin_candidate = services.resolve("all_plugins")
    except ServiceResolutionError:
        return None
    if not callable(plugin_candidate):
        return None
    plugin_loader = cast(Callable[[], SimpleNamespace], plugin_candidate)
    return plugin_loader()


def build_lint_runtime_context(
    state: PreparedLintStateView,
    *,
    config: ConfigProtocol,
    dependencies: LintRuntimeDependencies | None = None,
) -> LintRuntimeContext:
    """Create a :class:`LintRuntimeContext` ready for lint execution.

    Args:
        state: Prepared lint state derived from CLI inputs.
        config: Effective configuration built from the prepared options.
        dependencies: Optional overrides for registries, discovery factories,
            orchestrator construction, and shared services.

    Returns:
        LintRuntimeContext: Runtime bundle containing orchestrator, hooks, catalog
        snapshot, and optional resolved services/plugins.
    """

    deps = dependencies or DEFAULT_LINT_DEPENDENCIES
    catalog_snapshot = deps.catalog_initializer(deps.registry)
    ensure_internal_tools_registered(registry=deps.registry, state=state, config=config)
    configure_internal_tool_defaults(registry=deps.registry, state=state)
    hooks = OrchestratorHooks()
    discovery = deps.discovery_factory()
    orchestrator = deps.orchestrator_factory(
        deps.registry,
        discovery,
        hooks,
        state.logger.debug,
    )
    services = deps.services
    plugins = _resolve_plugin_namespace(services)
    return LintRuntimeContext(
        state=state,
        config=config,
        registry=deps.registry,
        orchestrator=orchestrator,
        hooks=hooks,
        catalog_snapshot=catalog_snapshot,
        services=services,
        plugins=plugins,
    )


__all__ = [
    "LintRuntimeContext",
    "LintRuntimeDependencies",
    "DEFAULT_LINT_DEPENDENCIES",
    "build_lint_runtime_context",
]
