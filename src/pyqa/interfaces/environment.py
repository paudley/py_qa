# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Interfaces for environment preparation and workspace detection."""

# pylint: disable=too-few-public-methods

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable


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
