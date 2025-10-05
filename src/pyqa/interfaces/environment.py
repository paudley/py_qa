"""Interfaces for environment preparation and workspace detection."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class EnvironmentPreparer(Protocol):
    """Prepare tool environments before execution."""

    def prepare(self) -> None:
        """Ensure the environment is ready for execution."""

        ...


@runtime_checkable
class RuntimeResolver(Protocol):
    """Resolve runtime executables for a tool invocation."""

    def resolve(self, tool: str) -> Path:
        """Return the executable path for ``tool``."""

        ...


@runtime_checkable
class WorkspaceLocator(Protocol):
    """Identify the active workspace root."""

    def locate(self) -> Path:
        """Return the root path of the workspace."""

        ...
