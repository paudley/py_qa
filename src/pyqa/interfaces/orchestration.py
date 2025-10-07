# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Execution orchestration contracts."""

# pylint: disable=too-few-public-methods -- Protocol definitions intentionally expose minimal method surfaces.

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from pyqa.core.environment.tool_env.models import PreparedCommand

    from ..config import Config
    from ..core.models import RunResult


@runtime_checkable
class ActionExecutor(Protocol):
    """Execute a single tool action."""

    def execute(self, action_name: str) -> None:
        """Run the action identified by ``action_name``.

        Args:
            action_name: Name of the action to execute.
        """
        raise NotImplementedError


@runtime_checkable
class RunHooks(Protocol):
    """Lifecycle callbacks invoked before/after pipeline stages."""

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

    def run(self, config: Config, *, root: Path) -> RunResult:
        """Execute tool actions for a configuration rooted at ``root``.

        Args:
            config: Configuration object describing the desired execution.
            root: Filesystem root used for discovery and execution context.

        Returns:
            RunResult: Aggregated result describing execution outcomes.
        """
        raise NotImplementedError

    def fetch_all_tools(
        self,
        config: Config,
        *,
        root: Path,
        callback: Callable[..., None] | None = None,
    ) -> Sequence[tuple[str, str, PreparedCommand | None, str | None]]:
        """Prepare all tools without executing them.

        Args:
            config: Configuration object controlling preparation behaviour.
            root: Filesystem root used for resolution of project paths.
            callback: Optional callback invoked for progress notifications.

        Returns:
            Sequence[tuple[str, str, PreparedCommand | None, str | None]]:
            Preparation results for each tool action (tool name, action name,
            prepared command metadata, optional error message).
        """
        raise NotImplementedError
