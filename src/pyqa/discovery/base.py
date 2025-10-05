# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Abstractions for locating files to lint."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence
from pathlib import Path
from typing import Protocol, runtime_checkable

from ..config import FileDiscoveryConfig


@runtime_checkable
class DiscoveryStrategy(Protocol):
    """Protocol implemented by discovery strategies.

    Implementers should provide lightweight file discovery routines that do
    not mutate global state and are safe to execute repeatedly.
    """

    def discover(self, config: FileDiscoveryConfig, root: Path) -> Iterable[Path]:
        """Yield discovered paths for ``root`` using ``config``.

        Args:
            config: File discovery configuration provided by the user.
            root: Repository root against which relative paths are resolved.

        Returns:
            Iterable[Path]: Iterator over resolved filesystem paths.

        Raises:
            NotImplementedError: Always raised; method must be provided by
                concrete strategy implementations.
        """

        raise NotImplementedError

    def __call__(self, config: FileDiscoveryConfig, root: Path) -> Iterable[Path]:
        """Invoke :meth:`discover` allowing strategies to be callable.

        Args:
            config: File discovery configuration provided by the user.
            root: Repository root against which relative paths are resolved.

        Returns:
            Iterable[Path]: Iterator over resolved filesystem paths.
        """
        raise NotImplementedError


class DiscoveryService:
    """Compose multiple discovery strategies into a single pipeline."""

    def __init__(self, strategies: Sequence[DiscoveryStrategy]):
        """Create a service that chains together ``strategies``.

        Args:
            strategies: Ordered discovery strategies to invoke sequentially.
        """
        self._strategies = tuple(strategies)

    def run(self, config: FileDiscoveryConfig, root: Path) -> list[Path]:
        """Execute all strategies and de-duplicate discovered paths.

        Args:
            config: Discovery configuration used by each strategy.
            root: Repository root relative to which discovery occurs.

        Returns:
            list[Path]: Ordered list of unique, resolved paths.
        """
        results: list[Path] = []
        seen: set[Path] = set()
        for strategy in self._strategies:
            for path in strategy.discover(config, root):
                resolved = path.resolve()
                if resolved in seen:
                    continue
                seen.add(resolved)
                results.append(resolved)
        return results

    def __iter__(self) -> Iterator[DiscoveryStrategy]:
        """Iterate over the composed discovery strategies."""

        return iter(self._strategies)

    def __len__(self) -> int:
        """Return the number of configured discovery strategies."""

        return len(self._strategies)

    def __contains__(self, strategy: object) -> bool:
        """Return whether ``strategy`` participates in this service."""

        return strategy in self._strategies


@runtime_checkable
class SupportsDiscovery(Protocol):
    """Duck-typed helper for components that expose a discovery interface."""

    def run(self, config: FileDiscoveryConfig, root: Path) -> list[Path]:
        """Execute discovery returning resolved filesystem paths.

        Args:
            config: File discovery configuration provided by the user.
            root: Repository root against which relative paths are resolved.

        Returns:
            list[Path]: Collection of resolved filesystem paths.

        Raises:
            NotImplementedError: Always raised; method must be provided by
                concrete discovery services.
        """

        raise NotImplementedError

    def __call__(self, config: FileDiscoveryConfig, root: Path) -> list[Path]:
        """Delegate to :meth:`run` enabling callable services."""
        raise NotImplementedError


def resolve_limit_paths(entries: Iterable[Path], root: Path) -> list[Path]:
    """Resolve ``entries`` against ``root`` returning unique absolute paths.

    Args:
        entries: Relative or absolute limit paths pulled from configuration.
        root: Repository root used to resolve relative entries.

    Returns:
        list[Path]: Ordered collection of unique, resolved limit paths.
    """

    resolved_limits: list[Path] = []
    for entry in entries:
        candidate = entry if entry.is_absolute() else root / entry
        resolved = candidate.resolve()
        if resolved not in resolved_limits:
            resolved_limits.append(resolved)
    return resolved_limits


def is_within_limits(candidate: Path, limits: Sequence[Path]) -> bool:
    """Return whether ``candidate`` is contained within any ``limits``.

    Args:
        candidate: Filesystem path to evaluate.
        limits: Sequence of absolute limit directories.

    Returns:
        bool: ``True`` when ``candidate`` is within any configured limit.
    """

    if not limits:
        return True
    return any(candidate.is_relative_to(limit) for limit in limits)


__all__ = [
    "DiscoveryStrategy",
    "DiscoveryService",
    "SupportsDiscovery",
    "resolve_limit_paths",
    "is_within_limits",
]
