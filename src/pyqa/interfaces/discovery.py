# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Interfaces for file discovery and target planning."""

from __future__ import annotations

from abc import abstractmethod
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:  # pragma: no cover - imported for type checking clarity
    from ..config import FileDiscoveryConfig


@runtime_checkable
class ExcludePolicy(Protocol):
    """Define a policy that returns paths excluded during discovery."""

    @property
    @abstractmethod
    def policy_name(self) -> str:
        """Return the unique name of the exclusion policy.

        Returns:
            str: Identifier describing the exclusion policy.
        """

        raise NotImplementedError

    @abstractmethod
    def exclusions(self) -> Sequence[str]:
        """Return exclusion patterns or paths.

        Returns:
            Sequence[str]: Exclusion patterns or filesystem paths.
        """

        raise NotImplementedError


@runtime_checkable
class TargetPlanner(Protocol):
    """Plan targets to feed into tool strategies."""

    @property
    @abstractmethod
    def planner_name(self) -> str:
        """Return the name of the planner implementation.

        Returns:
            str: Identifier describing the planner implementation.
        """

        raise NotImplementedError

    @abstractmethod
    def plan(self) -> Iterable[str]:
        """Return the ordered list of targets.

        Returns:
            Iterable[str]: Ordered collection of planned target identifiers.
        """

        raise NotImplementedError


@runtime_checkable
class DiscoveryStrategy(Protocol):
    """Perform discovery and yield filesystem paths for tooling."""

    @property
    @abstractmethod
    def identifier(self) -> str:
        """Return the discovery strategy identifier.

        Returns:
            str: Identifier describing the discovery strategy implementation.
        """

        raise NotImplementedError

    @abstractmethod
    def discover(self, config: FileDiscoveryConfig, root: Path) -> Iterable[Path]:
        """Return filesystem paths to process while applying discovery rules.

        Args:
            config: Discovery configuration supplied by the caller.
            root: Repository root used to resolve relative entries.

        Returns:
            Iterable[Path]: Resolved filesystem paths respecting discovery rules.
        """

        raise NotImplementedError

    def __call__(self, config: FileDiscoveryConfig, root: Path) -> Iterable[Path]:
        """Return discovery results while complying with callable expectations.

        Args:
            config: Discovery configuration supplied by the caller.
            root: Repository root used to resolve relative entries.

        Returns:
            Iterable[Path]: Resolved filesystem paths respecting discovery rules.
        """

        raise NotImplementedError


@runtime_checkable
class DiscoveryOptions(Protocol):
    """Target discovery options propagated to tooling layers."""

    @property
    def root(self) -> Path:
        """Return the filesystem root used when resolving targets.

        Returns:
            Path: Filesystem root for lint discovery.
        """

        raise NotImplementedError

    @property
    def paths(self) -> Sequence[Path]:
        """Return explicit file paths selected for discovery.

        Returns:
            Sequence[Path]: Files explicitly requested for discovery.
        """

        raise NotImplementedError

    @property
    def dirs(self) -> Sequence[Path]:
        """Return directory paths that should be recursively explored.

        Returns:
            Sequence[Path]: Directories to scan recursively.
        """

        raise NotImplementedError

    @property
    def exclude(self) -> Sequence[Path]:
        """Return paths that must be excluded from discovery.

        Returns:
            Sequence[Path]: Paths excluded from discovery.
        """

        raise NotImplementedError

    @property
    def include_dotfiles(self) -> bool:
        """Indicate whether dot-prefixed files should be included.

        Returns:
            bool: ``True`` when dotfiles should be considered.
        """

        raise NotImplementedError

    @property
    def paths_from_stdin(self) -> bool:
        """Return whether target paths were supplied via standard input.

        Returns:
            bool: ``True`` when target paths originated from standard input.
        """

        raise NotImplementedError


__all__ = [
    "DiscoveryStrategy",
    "ExcludePolicy",
    "TargetPlanner",
    "DiscoveryOptions",
]
