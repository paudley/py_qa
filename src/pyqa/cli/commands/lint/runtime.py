# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Runtime data structures and factories shared across lint CLI helpers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

from ....analysis.bootstrap import register_analysis_services
from ....catalog.model_catalog import CatalogSnapshot
from ....config import Config
from ....core.environment.tool_env.models import PreparedCommand
from ....core.models import RunResult
from ....discovery import build_default_discovery
from ....discovery.base import SupportsDiscovery
from ....interfaces.orchestration import ExecutionPipeline, OrchestratorHooks
from ....interfaces.orchestration_selection import SelectionResult
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
from .preparation import PreparedLintState


@dataclass(slots=True)
class LintRuntimeContext:
    """Bundle runtime dependencies for lint execution."""

    state: PreparedLintState
    config: Config
    registry: ToolRegistry
    orchestrator: ExecutionPipeline
    hooks: OrchestratorHooks
    catalog_snapshot: CatalogSnapshot
    services: ServiceContainer | None = None
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
    services: ServiceContainer | None = None


def _default_orchestrator_factory(
    registry: ToolRegistry,
    discovery: SupportsDiscovery,
    hooks: OrchestratorHooks,
    *,
    services: ServiceContainer | None = None,
    debug_logger: Callable[[str], None] | None = None,
) -> ExecutionPipeline:
    """Return an execution pipeline backed by the default orchestrator."""

    overrides = OrchestratorOverrides(
        hooks=_coerce_hooks(hooks),
        services=services,
        debug_logger=debug_logger,
    )
    orchestrator = Orchestrator(registry=registry, discovery=discovery, overrides=overrides)
    return _OrchestratorExecutionPipeline(orchestrator)


def _coerce_hooks(hooks: OrchestratorHooks) -> ConcreteOrchestratorHooks:
    """Return a concrete orchestrator hooks instance that proxies callbacks."""

    concrete = ConcreteOrchestratorHooks()

    def _proxy(name: str):
        def _call(*args, **kwargs):
            callback = getattr(hooks, name)
            if callback:
                callback(*args, **kwargs)

        return _call

    concrete.before_tool = _proxy("before_tool")
    concrete.after_tool = _proxy("after_tool")
    concrete.after_discovery = _proxy("after_discovery")
    concrete.after_execution = _proxy("after_execution")
    concrete.after_plan = _proxy("after_plan")
    return concrete


class _OrchestratorExecutionPipeline(ExecutionPipeline):
    """Execution pipeline backed by the core orchestrator implementation."""

    def __init__(self, orchestrator: Orchestrator) -> None:
        self._orchestrator = orchestrator

    @property
    def pipeline_name(self) -> str:
        """Return the descriptive pipeline name."""

        return "orchestrator"

    def run(self, config: Config, *, root: Path) -> RunResult:
        """Execute the orchestrator for ``config`` rooted at ``root``."""

        return self._orchestrator.run(config, root=root)

    def fetch_all_tools(
        self,
        config: Config,
        *,
        root: Path,
        callback: FetchCallback | None = None,
    ) -> list[tuple[str, str, PreparedCommand | None, str | None]]:
        """Prepare tool executions without running them."""

        return self._orchestrator.fetch_all_tools(config, root=root, callback=callback)

    def plan_tools(self, config: Config, *, root: Path) -> SelectionResult:
        """Return the orchestrator plan without executing actions."""

        return self._orchestrator.plan_tools(config, root=root)


_DEFAULT_SERVICES = ServiceContainer()
register_default_services(_DEFAULT_SERVICES)
register_analysis_services(_DEFAULT_SERVICES)


DEFAULT_LINT_DEPENDENCIES = LintRuntimeDependencies(
    registry=DEFAULT_REGISTRY,
    discovery_factory=build_default_discovery,
    orchestrator_factory=lambda registry, discovery, hooks, debug_logger=None: _default_orchestrator_factory(
        registry,
        discovery,
        hooks,
        services=_DEFAULT_SERVICES,
        debug_logger=debug_logger,
    ),
    catalog_initializer=lambda registry: initialize_registry(registry=registry),
    services=_DEFAULT_SERVICES,
)


def build_lint_runtime_context(
    state: PreparedLintState,
    *,
    config: Config,
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
    plugins: SimpleNamespace | None = None
    if services is not None:
        try:
            load_plugins = services.resolve("all_plugins")
        except ServiceResolutionError:
            load_plugins = None
        if load_plugins is not None:
            plugins = load_plugins()
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
