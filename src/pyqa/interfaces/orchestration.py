# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Execution orchestration contracts."""

# pylint: disable=too-few-public-methods

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ActionExecutor(Protocol):
    """Execute a single tool action."""

    def execute(self, action_name: str) -> None:
        """Run the action identified by ``action_name``."""
        raise NotImplementedError


@runtime_checkable
class RunHooks(Protocol):
    """Lifecycle callbacks invoked before/after pipeline stages."""

    def before_phase(self, phase: str) -> None:
        """Called before executing ``phase``."""
        raise NotImplementedError

    def after_phase(self, phase: str) -> None:
        """Called after executing ``phase``."""
        raise NotImplementedError


@runtime_checkable
class ExecutionPipeline(Protocol):
    """Coordinate tool execution phases."""

    def run(self, hooks: RunHooks | None = None) -> None:
        """Execute the pipeline and invoke optional ``hooks``."""
        raise NotImplementedError
