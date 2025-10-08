# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Adapters bridging orchestration implementations to CLI interfaces."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from pyqa.config import Config
from pyqa.core.environment.tool_env.models import PreparedCommand
from pyqa.core.models import RunResult
from pyqa.core.runtime.di import ServiceContainer
from pyqa.discovery.base import SupportsDiscovery
from pyqa.interfaces.orchestration import ExecutionPipeline
from pyqa.orchestration.orchestrator import (
    FetchCallback,
    Orchestrator,
    OrchestratorHooks,
    OrchestratorOverrides,
)
from pyqa.orchestration.tool_selection import SelectionResult
from pyqa.tools.registry import ToolRegistry


class OrchestratorExecutionPipeline(ExecutionPipeline):
    """Adapter exposing :class:`Orchestrator` through the pipeline protocol."""

    def __init__(self, orchestrator: Orchestrator) -> None:
        self._orchestrator = orchestrator

    @property
    def pipeline_name(self) -> str:
        """Return the human-readable name for this execution pipeline."""

        return "orchestrator"

    def run(self, config: Config, *, root: Path) -> RunResult:
        """Execute the orchestrator for ``config`` rooted at ``root``.

        Args:
            config: Normalised configuration describing the desired execution.
            root: Filesystem root supplied to discovery and tool execution.

        Returns:
            RunResult: Aggregated outcomes produced by the orchestrator.
        """

        return self._orchestrator.run(config, root=root)

    def fetch_all_tools(
        self,
        config: Config,
        *,
        root: Path,
        callback: FetchCallback | None = None,
    ) -> list[tuple[str, str, PreparedCommand | None, str | None]]:
        """Prepare tool actions without executing them.

        Args:
            config: Configuration controlling preparation behaviour.
            root: Filesystem root supplied to preparation logic.
            callback: Optional progress callback invoked per prepared action.

        Returns:
            list[tuple[str, str, PreparedCommand | None, str | None]]: Sequence of
            preparation results for each tool action.
        """

        return self._orchestrator.fetch_all_tools(config, root=root, callback=callback)

    def plan_tools(self, config: Config, *, root: Path) -> SelectionResult:
        """Return the planned tool execution order without running the orchestrator."""

        return self._orchestrator.plan_tools(config, root=root)


def build_orchestrator_pipeline(
    registry: ToolRegistry,
    discovery: SupportsDiscovery,
    hooks: OrchestratorHooks,
    *,
    services: ServiceContainer | None = None,
    debug_logger: Callable[[str], None] | None = None,
) -> ExecutionPipeline:
    """Return an execution pipeline backed by :class:`Orchestrator`.

    Args:
        registry: Tool registry resolving available tooling implementations.
        discovery: Discovery strategy used to gather candidate files.
        hooks: Hook container receiving progress callbacks.
        services: Optional service container supplying shared factories.

    Returns:
        ExecutionPipeline: Adapter exposing the underlying orchestrator through
        the interface consumed by CLI modules.
    """

    overrides = OrchestratorOverrides(
        hooks=hooks,
        services=services,
        debug_logger=debug_logger,
    )
    orchestrator = Orchestrator(registry=registry, discovery=discovery, overrides=overrides)
    return OrchestratorExecutionPipeline(orchestrator)


__all__ = [
    "OrchestratorExecutionPipeline",
    "build_orchestrator_pipeline",
]
