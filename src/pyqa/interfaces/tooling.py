# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Interfaces describing tooling installation and bootstrap flows."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class Installer(Protocol):
    """Install or update external tooling managed by pyqa."""

    @property
    def tool_name(self) -> str:
        """Return the tool handled by this installer."""

        raise NotImplementedError

    def install(self, *, root: Path, dry_run: bool = False) -> None:
        """Install tooling into ``root`` optionally as a dry run."""

        raise NotImplementedError


@runtime_checkable
class RuntimeBootstrapper(Protocol):
    """Prepare runtime environments for command execution."""

    @property
    def bootstrapper_name(self) -> str:
        """Return the identifier for the bootstrapper implementation."""

        raise NotImplementedError

    def bootstrap(self, *, root: Path) -> None:
        """Ensure the runtime dependencies for ``root`` are ready."""

        raise NotImplementedError


__all__ = ["Installer", "RuntimeBootstrapper"]
