# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Interfaces describing tooling installation and bootstrap flows."""

from __future__ import annotations

from abc import abstractmethod
from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class Installer(Protocol):
    """Install or update external tooling managed by pyqa."""

    @property
    @abstractmethod
    def tool_name(self) -> str:
        """Return the identifier of the tool handled by this installer.

        Returns:
            str: Identifier for the tool managed by the installer.
        """

        raise NotImplementedError

    @abstractmethod
    def install(self, *, root: Path, dry_run: bool = False) -> None:
        """Perform tooling installation into ``root`` optionally as a dry run.

        Args:
            root: Repository root where tooling should be installed.
            dry_run: When ``True`` report actions without performing changes.
        """
        raise NotImplementedError


@runtime_checkable
class RuntimeBootstrapper(Protocol):
    """Prepare runtime environments for command execution."""

    @property
    @abstractmethod
    def bootstrapper_name(self) -> str:
        """Return the identifier for the bootstrapper implementation.

        Returns:
            str: Identifier describing the bootstrapper implementation.
        """

        raise NotImplementedError

    @abstractmethod
    def bootstrap(self, *, root: Path) -> None:
        """Ensure the runtime dependencies for ``root`` are ready.

        Args:
            root: Repository root requiring runtime preparation.
        """
        raise NotImplementedError


__all__ = ["Installer", "RuntimeBootstrapper"]
