# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Interfaces for file discovery and target planning."""

# pylint: disable=too-few-public-methods -- Protocol definitions intentionally expose minimal method surfaces.

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:  # pragma: no cover - imported for type checking clarity
    from ..config import FileDiscoveryConfig


@runtime_checkable
class ExcludePolicy(Protocol):
    """Return paths that should be excluded during discovery."""

    def exclusions(self) -> Sequence[str]:
        """Return exclusion patterns or paths."""
        raise NotImplementedError


@runtime_checkable
class TargetPlanner(Protocol):
    """Plan targets to feed into tool strategies."""

    def plan(self) -> Iterable[str]:
        """Return the ordered list of targets."""
        raise NotImplementedError


@runtime_checkable
class DiscoveryStrategy(Protocol):
    """Perform discovery and yield filesystem paths for tooling."""

    def discover(self, config: FileDiscoveryConfig, root: Path) -> Iterable[Path]:
        """Yield resolved filesystem paths to process.

        Args:
            config: Discovery configuration supplied by the caller.
            root: Repository root used to resolve relative entries.

        Returns:
            Iterable[Path]: Resolved filesystem paths respecting discovery rules.
        """
        raise NotImplementedError

    def __call__(self, config: FileDiscoveryConfig, root: Path) -> Iterable[Path]:
        """Delegate to :meth:`discover` for callable compatibility."""
        raise NotImplementedError
