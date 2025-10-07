# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Interfaces for environment preparation and workspace detection."""

# pylint: disable=too-few-public-methods -- Protocol definitions intentionally expose minimal method surfaces.

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class EnvironmentPreparer(Protocol):
    """Prepare tool environments before execution."""

    def prepare(self) -> None:
        """Ensure the environment is ready for execution."""
        raise NotImplementedError


@runtime_checkable
class RuntimeResolver(Protocol):
    """Resolve runtime executables for a tool invocation."""

    def resolve(self, tool: str) -> Path:
        """Return the executable path for ``tool``."""
        raise NotImplementedError


@runtime_checkable
class WorkspaceLocator(Protocol):
    """Identify the active workspace root."""

    def locate(self) -> Path:
        """Return the root path of the workspace."""
        raise NotImplementedError


@runtime_checkable
class EnvironmentInspector(Protocol):
    """Inspect the active execution environment for useful metadata."""

    def inspect(self, project_root: Path) -> dict[str, Any]:
        """Return structured metadata for ``project_root``."""

        raise NotImplementedError


@runtime_checkable
class VirtualEnvDetector(Protocol):
    """Locate virtual environments associated with a project."""

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
