# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Interfaces for environment preparation and workspace detection."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class EnvironmentPreparer(Protocol):
    """Prepare tool environments before execution."""

    @property
    def preparer_name(self) -> str:
        """Return the name of the preparer implementation."""
        raise NotImplementedError("EnvironmentPreparer.preparer_name must be implemented")

    def prepare(self) -> None:
        """Ensure the environment is ready for execution."""
        raise NotImplementedError


@runtime_checkable
class RuntimeResolver(Protocol):
    """Resolve runtime executables for a tool invocation."""

    @property
    def supported_tools(self) -> tuple[str, ...]:
        """Return the tuple of tools handled by the resolver."""
        raise NotImplementedError("RuntimeResolver.supported_tools must be implemented")

    def resolve(self, tool: str) -> Path:
        """Return the executable path for ``tool``."""
        raise NotImplementedError


@runtime_checkable
class WorkspaceLocator(Protocol):
    """Identify the active workspace root."""

    @property
    def workspace_hint(self) -> str:
        """Return a descriptive hint of the workspace type."""
        raise NotImplementedError("WorkspaceLocator.workspace_hint must be implemented")

    def locate(self) -> Path:
        """Return the root path of the workspace."""
        raise NotImplementedError


@runtime_checkable
class EnvironmentInspector(Protocol):
    """Inspect the active execution environment for useful metadata."""

    @property
    def inspector_name(self) -> str:
        """Return the identifier of the inspector implementation."""
        raise NotImplementedError("EnvironmentInspector.inspector_name must be implemented")

    def inspect(self, project_root: Path) -> dict[str, Any]:
        """Return structured metadata for ``project_root``."""

        raise NotImplementedError


@runtime_checkable
class VirtualEnvDetector(Protocol):
    """Locate virtual environments associated with a project."""

    @property
    def supported_managers(self) -> tuple[str, ...]:
        """Return the supported virtual environment managers."""
        raise NotImplementedError("VirtualEnvDetector.supported_managers must be implemented")

    def find(self, project_root: Path) -> Path | None:
        """Return the virtualenv path for ``project_root`` when available."""

        raise NotImplementedError


__all__ = [
    "EnvironmentInspector",
    "EnvironmentPreparer",
    "RuntimeResolver",
    "VirtualEnvDetector",
    "WorkspaceLocator",
]
