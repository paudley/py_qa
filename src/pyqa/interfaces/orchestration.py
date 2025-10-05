"""Execution orchestration contracts."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ActionExecutor(Protocol):
    """Execute a single tool action."""

    def execute(self, action_name: str) -> None:
        """Run the action identified by ``action_name``."""

        ...


@runtime_checkable
class RunHooks(Protocol):
    """Lifecycle callbacks invoked before/after pipeline stages."""

    def before_phase(self, phase: str) -> None:
        """Called before executing ``phase``."""

        ...

    def after_phase(self, phase: str) -> None:
        """Called after executing ``phase``."""

        ...


@runtime_checkable
class ExecutionPipeline(Protocol):
    """Coordinate tool execution phases."""

    def run(self, hooks: RunHooks | None = None) -> None:
        """Execute the pipeline and invoke optional ``hooks``."""

        ...
