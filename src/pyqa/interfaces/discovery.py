"""Interfaces for file discovery and target planning."""

from __future__ import annotations

from typing import Protocol, runtime_checkable
from collections.abc import Iterable, Sequence


@runtime_checkable
class ExcludePolicy(Protocol):
    """Return paths that should be excluded during discovery."""

    def exclusions(self) -> Sequence[str]:
        """Return exclusion patterns or paths."""

        ...


@runtime_checkable
class TargetPlanner(Protocol):
    """Plan targets to feed into tool strategies."""

    def plan(self) -> Iterable[str]:
        """Return the ordered list of targets."""

        ...


@runtime_checkable
class DiscoveryStrategy(Protocol):
    """Perform discovery and return a planner/policy tuple."""

    def build(self) -> tuple[TargetPlanner, ExcludePolicy]:
        """Return planners and exclude policies for downstream use."""

        ...
