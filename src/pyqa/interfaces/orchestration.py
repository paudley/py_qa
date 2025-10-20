# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Execution orchestration contracts."""

from __future__ import annotations

from abc import abstractmethod
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
    @abstractmethod
    def executor_name(self) -> str:
        """Return the identifier of the executor implementation.

        Returns:
            str: Identifier describing the executor implementation.
        """
        raise NotImplementedError

    @abstractmethod
    def execute(self, action_name: str) -> None:
        """Run the action identified by ``action_name``.

        Args:
            action_name: Name of the action to execute.
        """
        raise NotImplementedError


@runtime_checkable
class RunHooks(Protocol):
    """Provide lifecycle callbacks invoked before/after pipeline stages."""

    @property
    @abstractmethod
    def supported_phases(self) -> Sequence[str]:
        """Return the ordered phases for which hooks are registered.

        Returns:
            Sequence[str]: Ordered phases understood by the hook collection.
        """
        raise NotImplementedError

    @abstractmethod
    def before_phase(self, phase: str) -> None:
        """Run hook logic before executing ``phase``.

        Args:
            phase: Phase identifier about to be executed.
        """
        raise NotImplementedError

    @abstractmethod
    def after_phase(self, phase: str) -> None:
        """Run hook logic after executing ``phase``.

        Args:
            phase: Phase identifier that completed execution.
        """
        raise NotImplementedError


@runtime_checkable
class ExecutionPipeline(Protocol):
    """Coordinate tool execution phases."""

    @property
    @abstractmethod
    def pipeline_name(self) -> str:
        """Return the name of the execution pipeline.

        Returns:
            str: Identifier describing the execution pipeline implementation.
        """
        raise NotImplementedError

    @abstractmethod
    def run(self, config: Config, *, root: Path) -> RunResult:
        """Run the execution pipeline for ``config`` rooted at ``root``.

        Args:
            config: Configuration object describing the desired execution.
            root: Filesystem root used for discovery and execution context.

        Returns:
            RunResult: Aggregated result describing execution outcomes.
        """
        raise NotImplementedError

    @abstractmethod
    def plan_tools(self, config: Config, *, root: Path) -> SelectionResult:
        """Return the planned tool execution order without running them.

        Args:
            config: Configuration used to determine eligible tools.
            root: Repository root guiding discovery.

        Returns:
            SelectionResult: Planned tool ordering and decision metadata.
        """
        raise NotImplementedError

    @abstractmethod
    def fetch_all_tools(
        self,
        config: Config,
        *,
        root: Path,
        callback: Callable[..., None] | None = None,
    ) -> Sequence[tuple[str, str, PreparedCommand | None, str | None]]:
        """Prepare all tools without executing them.

        Args:
            config: Configuration used to prepare tooling.
            root: Repository root guiding preparation.
            callback: Optional callback invoked as tools are prepared.

        Returns:
            Sequence[tuple[str, str, PreparedCommand | None, str | None]]:
                Prepared tooling descriptors describing the available commands.
        """
        raise NotImplementedError


@dataclass(slots=True)
class OrchestratorHooks:
    """Provide lifecycle callbacks invoked around orchestration phases."""

    before_tool: Callable[[str], None] | None = None
    after_tool: Callable[[ToolOutcome], None] | None = None
    after_discovery: Callable[[int], None] | None = None
    after_execution: Callable[[RunResult], None] | None = None
    after_plan: Callable[[int], None] | None = None
