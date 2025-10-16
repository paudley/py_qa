# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Interfaces for environment preparation and workspace detection."""

from __future__ import annotations

from abc import abstractmethod
from pathlib import Path
from typing import Protocol, runtime_checkable

from pyqa.core.serialization import JsonValue


@runtime_checkable
class EnvironmentPreparer(Protocol):
    """Prepare tool environments before execution."""

    @property
    @abstractmethod
    def preparer_name(self) -> str:
        """Return the name of the preparer implementation.

        Returns:
            str: Identifier describing the environment preparer implementation.
        """
        raise NotImplementedError

    @abstractmethod
    def prepare(self) -> None:
        """Ensure the environment is ready for execution."""
        raise NotImplementedError


@runtime_checkable
class RuntimeResolver(Protocol):
    """Resolve runtime executables for a tool invocation."""

    @property
    @abstractmethod
    def supported_tools(self) -> tuple[str, ...]:
        """Return the tuple of tools handled by the resolver.

        Returns:
            tuple[str, ...]: Tool identifiers supported by the resolver.
        """
        raise NotImplementedError

    @abstractmethod
    def resolve(self, tool: str) -> Path:
        """Return the executable path for ``tool``.

        Args:
            tool: Tool identifier requiring resolution.

        Returns:
            Path: Resolves executable path for the requested tool.
        """
        raise NotImplementedError


@runtime_checkable
class WorkspaceLocator(Protocol):
    """Identify the active workspace root."""

    @property
    @abstractmethod
    def workspace_hint(self) -> str:
        """Return a descriptive hint of the workspace type.

        Returns:
            str: Descriptive hint summarising the detected workspace.
        """
        raise NotImplementedError

    @abstractmethod
    def locate(self) -> Path:
        """Return the root path of the workspace.

        Returns:
            Path: Root path of the detected workspace.
        """
        raise NotImplementedError


@runtime_checkable
class EnvironmentInspector(Protocol):
    """Inspect the active execution environment for useful metadata."""

    @property
    @abstractmethod
    def inspector_name(self) -> str:
        """Return the identifier of the inspector implementation.

        Returns:
            str: Identifier describing the environment inspector.
        """
        raise NotImplementedError

    @abstractmethod
    def inspect(self, project_root: Path) -> dict[str, JsonValue]:
        """Return structured metadata for ``project_root``.

        Args:
            project_root: Root path whose environment should be inspected.

        Returns:
            dict[str, JsonValue]: Metadata describing the execution environment.
        """
        raise NotImplementedError


@runtime_checkable
class VirtualEnvDetector(Protocol):
    """Provide detection for project-specific virtual environments."""

    @property
    @abstractmethod
    def supported_managers(self) -> tuple[str, ...]:
        """Return the supported virtual environment managers.

        Returns:
            tuple[str, ...]: Identifiers for the supported environment managers.
        """
        raise NotImplementedError

    @abstractmethod
    def find(self, project_root: Path) -> Path | None:
        """Return the virtualenv path for ``project_root`` when available.

        Args:
            project_root: Root path associated with the project being inspected.

        Returns:
            Path | None: Resolved virtual environment path when detected; otherwise ``None``.
        """
        raise NotImplementedError


__all__ = [
    "EnvironmentInspector",
    "EnvironmentPreparer",
    "RuntimeResolver",
    "VirtualEnvDetector",
    "WorkspaceLocator",
]
