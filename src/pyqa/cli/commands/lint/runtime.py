# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Runtime data structures and factories shared across lint CLI helpers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from types import SimpleNamespace

from ....catalog.model_catalog import CatalogSnapshot
from ....config import Config
from ....discovery import build_default_discovery
from ....discovery.base import SupportsDiscovery
from ....interfaces.orchestration import ExecutionPipeline
from ....orchestration.orchestrator import OrchestratorHooks
from ....tools.builtin_registry import initialize_registry
from ....tools.registry import DEFAULT_REGISTRY, ToolRegistry
from ...core.orchestration import build_orchestrator_pipeline
from ...core.runtime import ServiceContainer, ServiceResolutionError, register_default_services
from .preparation import PreparedLintState


@dataclass(slots=True)
class LintRuntimeContext:
    """Bundle runtime dependencies for lint execution."""

    state: PreparedLintState
    config: Config
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
    orchestrator_factory: Callable[[ToolRegistry, SupportsDiscovery, OrchestratorHooks], ExecutionPipeline]
    catalog_initializer: Callable[[ToolRegistry], CatalogSnapshot]
    services: ServiceContainer | None = None


def _default_orchestrator_factory(
    registry: ToolRegistry,
    discovery: SupportsDiscovery,
    hooks: OrchestratorHooks,
    *,
    services: ServiceContainer | None = None,
) -> ExecutionPipeline:
    """Return an execution pipeline backed by the default orchestrator.

    Args:
        registry: Tool registry used to resolve available tools.
        discovery: Discovery strategy responsible for locating project files.
        hooks: Hook container receiving lifecycle callbacks.
        services: Optional service container supplying shared factories.

    Returns:
        ExecutionPipeline: Pipeline adapter wrapping the orchestrator instance.
    """

    return build_orchestrator_pipeline(
        registry=registry,
        discovery=discovery,
        hooks=hooks,
        services=services,
    )


_DEFAULT_SERVICES = ServiceContainer()
register_default_services(_DEFAULT_SERVICES)


DEFAULT_LINT_DEPENDENCIES = LintRuntimeDependencies(
    registry=DEFAULT_REGISTRY,
    discovery_factory=build_default_discovery,
    orchestrator_factory=lambda registry, discovery, hooks: _default_orchestrator_factory(
        registry,
        discovery,
        hooks,
        services=_DEFAULT_SERVICES,
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
    hooks = OrchestratorHooks()
    discovery = deps.discovery_factory()
    orchestrator = deps.orchestrator_factory(deps.registry, discovery, hooks)
    catalog_snapshot = deps.catalog_initializer(deps.registry)
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
