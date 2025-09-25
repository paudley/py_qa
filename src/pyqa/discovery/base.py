# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Abstractions for locating files to lint."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Protocol

from ..config import FileDiscoveryConfig


class DiscoveryStrategy(Protocol):
    """Protocol implemented by discovery strategies."""

    def discover(self, config: FileDiscoveryConfig, root: Path) -> Iterable[Path]: ...


class DiscoveryService:
    """Compose multiple discovery strategies into a single pipeline."""

    def __init__(self, strategies: Sequence[DiscoveryStrategy]):
        self._strategies = tuple(strategies)

    def run(self, config: FileDiscoveryConfig, root: Path) -> list[Path]:
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


class SupportsDiscovery(Protocol):
    """Duck-typed helper for components that expose a discovery interface."""

    def run(self, config: FileDiscoveryConfig, root: Path) -> list[Path]: ...
