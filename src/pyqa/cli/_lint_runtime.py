# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Runtime data structures and factories shared across lint CLI helpers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ..config import Config
from ..discovery import build_default_discovery
from ..discovery.base import SupportsDiscovery
from ..execution.orchestrator import Orchestrator, OrchestratorHooks, OrchestratorOverrides
from ..tooling.catalog.model_catalog import CatalogSnapshot
from ..tools.builtin_registry import initialize_registry
from ..tools.registry import DEFAULT_REGISTRY, ToolRegistry
from ._lint_preparation import PreparedLintState


@dataclass(slots=True)
class LintRuntimeContext:
    """Bundle runtime dependencies for lint execution."""

    state: PreparedLintState
    config: Config
    orchestrator: Orchestrator
    hooks: OrchestratorHooks
    catalog_snapshot: CatalogSnapshot


@dataclass(slots=True)
class LintRuntimeDependencies:
    """Collaborators required to construct :class:`LintRuntimeContext`."""

    registry: ToolRegistry
    discovery_factory: Callable[[], SupportsDiscovery]
    orchestrator_factory: Callable[[ToolRegistry, SupportsDiscovery, OrchestratorHooks], Orchestrator]
    catalog_initializer: Callable[[ToolRegistry], CatalogSnapshot]


def _default_orchestrator_factory(
    registry: ToolRegistry,
    discovery: SupportsDiscovery,
    hooks: OrchestratorHooks,
) -> Orchestrator:
    """Create an :class:`Orchestrator` using the provided collaborators.

    Args:
        registry: Tool registry used to resolve available tools.
        discovery: Discovery strategy responsible for locating project files.
        hooks: Hook container that receives orchestration lifecycle callbacks.

    Returns:
        Orchestrator: Configured orchestrator instance.
    """

    overrides = OrchestratorOverrides(hooks=hooks)
    return Orchestrator(registry=registry, discovery=discovery, overrides=overrides)


DEFAULT_LINT_DEPENDENCIES = LintRuntimeDependencies(
    registry=DEFAULT_REGISTRY,
    discovery_factory=build_default_discovery,
    orchestrator_factory=_default_orchestrator_factory,
    catalog_initializer=lambda registry: initialize_registry(registry=registry),
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
            and orchestrator construction.

    Returns:
        LintRuntimeContext: Runtime bundle containing orchestrator, hooks, and
        catalog snapshot.
    """

    deps = dependencies or DEFAULT_LINT_DEPENDENCIES
    hooks = OrchestratorHooks()
    discovery = deps.discovery_factory()
    orchestrator = deps.orchestrator_factory(deps.registry, discovery, hooks)
    catalog_snapshot = deps.catalog_initializer(deps.registry)
    return LintRuntimeContext(
        state=state,
        config=config,
        orchestrator=orchestrator,
        hooks=hooks,
        catalog_snapshot=catalog_snapshot,
    )


__all__ = [
    "LintRuntimeContext",
    "LintRuntimeDependencies",
    "DEFAULT_LINT_DEPENDENCIES",
    "build_lint_runtime_context",
]
