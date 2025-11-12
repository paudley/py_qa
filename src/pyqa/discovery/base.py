# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Abstractions for locating files to lint."""

from __future__ import annotations

from abc import abstractmethod
from collections.abc import Iterable, Iterator, Sequence
from pathlib import Path
from typing import Protocol, runtime_checkable

from ..interfaces.discovery import DiscoveryStrategy as DiscoveryStrategyProtocol
from ..interfaces.discovery import (
    FileDiscoveryConfig,
)


@runtime_checkable
class DiscoveryStrategy(DiscoveryStrategyProtocol, Protocol):
    """Protocol implemented by discovery strategies.

    Concrete implementations should provide a lightweight :meth:`discover`
    method that yields resolved file paths without mutating global state.
    """

    def __call__(self, config: FileDiscoveryConfig, root: Path) -> Iterable[Path]:
        """Delegate to :meth:`discover` enabling callable semantics.

        Args:
            config: Discovery configuration supplied by the caller.
            root: Repository root used to resolve relative paths.

        Returns:
            Iterable[Path]: Iterable yielding resolved filesystem paths.
        """

        return self.discover(config, root)


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
        """Iterate over the composed discovery strategies.

        Returns:
            Iterator[DiscoveryStrategy]: Iterator yielding the configured strategies.
        """

        return iter(self._strategies)

    def __len__(self) -> int:
        """Return the number of configured discovery strategies.

        Returns:
            int: Count of strategies participating in discovery.
        """

        return len(self._strategies)

    def __contains__(self, strategy: DiscoveryStrategy) -> bool:
        """Return whether ``strategy`` participates in this service.

        Args:
            strategy: Discovery strategy to test for membership.

        Returns:
            bool: ``True`` when ``strategy`` is part of this service.
        """

        return strategy in self._strategies


class DiscoveryProtocolError(RuntimeError):
    """Raised when discovery protocol methods are invoked without implementations."""


@runtime_checkable
class SupportsDiscovery(Protocol):
    """Duck-typed helper for components that expose a discovery interface."""

    @abstractmethod
    def run(self, config: FileDiscoveryConfig, root: Path) -> list[Path]:
        """Execute discovery returning resolved filesystem paths.

        Args:
            config: File discovery configuration provided by the user.
            root: Repository root against which relative paths are resolved.

        Returns:
            list[Path]: Collection of resolved filesystem paths.

        Raises:
            DiscoveryProtocolError: Raised when the implementation does not override ``run``.
        """

        msg = "SupportsDiscovery implementations must override run() to provide discovery behaviour."
        raise DiscoveryProtocolError(msg)

    def __call__(self, config: FileDiscoveryConfig, root: Path) -> list[Path]:
        """Delegate to :meth:`run` enabling callable services.

        Args:
            config: File discovery configuration supplied by the caller.
            root: Repository root used to resolve relative paths.

        Returns:
            list[Path]: Results returned by :meth:`run`.
        """

        return self.run(config, root)


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
