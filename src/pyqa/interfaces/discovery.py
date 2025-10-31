# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Interfaces for file discovery and target planning."""

from __future__ import annotations

from abc import abstractmethod
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Protocol, Self, TypeAlias, cast, runtime_checkable

from .common import PathSelectionOptions

DiscoveryConfigValue: TypeAlias = Path | Sequence[Path] | bool | str | None


@runtime_checkable
class FileDiscoveryConfig(Protocol):
    """Discovery configuration supplied by CLI and configuration layers."""

    roots: list[Path]
    excludes: list[Path]
    explicit_files: list[Path]
    limit_to: list[Path]
    paths_from_stdin: bool
    changed_only: bool
    diff_ref: str | None
    include_untracked: bool
    base_branch: str | None
    pre_commit: bool

    def model_copy(
        self,
        *,
        update: Mapping[str, DiscoveryConfigValue] | None = None,
        deep: bool = False,
    ) -> Self:
        """Return a mutated copy of the discovery configuration.

        Args:
            update: Optional mapping of field updates to apply.
            deep: When ``True`` perform a deep copy instead of a shallow copy.

        Returns:
            Self: Updated discovery configuration copy.
        """
        raise NotImplementedError

    def model_dump(self) -> Mapping[str, DiscoveryConfigValue]:
        """Return a mapping representation of the discovery configuration.

        Returns:
            Mapping[str, DiscoveryConfigValue]: Mapping of discovery fields to values.
        """
        return cast(Mapping[str, DiscoveryConfigValue], NotImplemented)


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

        ...

    @abstractmethod
    def exclusions(self) -> Sequence[str]:
        """Return exclusion patterns or paths.

        Returns:
            Sequence[str]: Exclusion patterns or filesystem paths.
        """

        ...


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

        ...

    @abstractmethod
    def plan(self) -> Iterable[str]:
        """Return the ordered list of targets.

        Returns:
            Iterable[str]: Ordered collection of planned target identifiers.
        """

        ...


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

        ...

    @abstractmethod
    def discover(self, config: FileDiscoveryConfig, root: Path) -> Iterable[Path]:
        """Return filesystem paths to process while applying discovery rules.

        Args:
            config: Discovery configuration supplied by the caller.
            root: Repository root used to resolve relative entries.

        Returns:
            Iterable[Path]: Resolved filesystem paths respecting discovery rules.
        """

        ...

    def __call__(self, config: FileDiscoveryConfig, root: Path) -> Iterable[Path]:
        """Return discovery results while complying with callable expectations.

        Args:
            config: Discovery configuration supplied by the caller.
            root: Repository root used to resolve relative entries.

        Returns:
            Iterable[Path]: Resolved filesystem paths respecting discovery rules.
        """

        ...


@runtime_checkable
class DiscoveryOptions(PathSelectionOptions, Protocol):
    """Target discovery options propagated to tooling layers."""


__all__ = [
    "DiscoveryStrategy",
    "ExcludePolicy",
    "FileDiscoveryConfig",
    "TargetPlanner",
    "DiscoveryOptions",
]
