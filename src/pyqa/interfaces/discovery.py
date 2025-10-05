# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Interfaces for file discovery and target planning."""

# pylint: disable=too-few-public-methods

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Protocol, runtime_checkable


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
    """Perform discovery and return a planner/policy tuple."""

    def build(self) -> tuple[TargetPlanner, ExcludePolicy]:
        """Return planners and exclude policies for downstream use."""
        raise NotImplementedError
