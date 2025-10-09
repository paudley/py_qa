# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Execution orchestration contracts."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from pyqa.core.environment.tool_env.models import PreparedCommand

    from ..config import Config
    from ..core.models import RunResult, ToolOutcome
    from .orchestration_selection import SelectionResult


@runtime_checkable
class ActionExecutor(Protocol):
    """Execute a single tool action."""

    @property
    def executor_name(self) -> str:
        """Return the identifier of the executor implementation."""
        raise NotImplementedError("ActionExecutor.executor_name must be implemented")

    def execute(self, action_name: str) -> None:
        """Run the action identified by ``action_name``.

        Args:
            action_name: Name of the action to execute.
        """
        raise NotImplementedError


@runtime_checkable
class RunHooks(Protocol):
    """Lifecycle callbacks invoked before/after pipeline stages."""

    @property
    def supported_phases(self) -> Sequence[str]:
        """Return the ordered phases for which hooks are registered."""
        raise NotImplementedError("RunHooks.supported_phases must be implemented")

    def before_phase(self, phase: str) -> None:
        """Called before executing ``phase``.

        Args:
            phase: Phase identifier about to be executed.
        """
        raise NotImplementedError

    def after_phase(self, phase: str) -> None:
        """Called after executing ``phase``.

        Args:
            phase: Phase identifier that completed execution.
        """
        raise NotImplementedError


@runtime_checkable
class ExecutionPipeline(Protocol):
    """Coordinate tool execution phases."""

    @property
    def pipeline_name(self) -> str:
        """Return the name of the execution pipeline."""
        raise NotImplementedError("ExecutionPipeline.pipeline_name must be implemented")

    def run(self, config: Config, *, root: Path) -> RunResult:
        """Execute tool actions for a configuration rooted at ``root``.

        Args:
            config: Configuration object describing the desired execution.
            root: Filesystem root used for discovery and execution context.

        Returns:
            RunResult: Aggregated result describing execution outcomes.
        """
        raise NotImplementedError

    def plan_tools(self, config: Config, *, root: Path) -> SelectionResult:
        """Return the planned tool execution order without running them."""

        raise NotImplementedError

    def fetch_all_tools(
        self,
        config: Config,
        *,
        root: Path,
        callback: Callable[..., None] | None = None,
    ) -> Sequence[tuple[str, str, PreparedCommand | None, str | None]]:
        """Prepare all tools without executing them."""

        raise NotImplementedError


@dataclass(slots=True)
class OrchestratorHooks:
    """Lifecycle callbacks invoked around orchestration phases."""

    before_tool: Callable[[str], None] | None = None
    after_tool: Callable[[ToolOutcome], None] | None = None
    after_discovery: Callable[[int], None] | None = None
    after_execution: Callable[[RunResult], None] | None = None
    after_plan: Callable[[int], None] | None = None

    @property
    def supported_phases(self) -> Sequence[str]:
        """Return lifecycle phases that may trigger hooks."""

        return ("plan", "discovery", "tool", "execution")
