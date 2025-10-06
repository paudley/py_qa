# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Catalog contracts for tool definitions and strategies."""

# pylint: disable=too-few-public-methods

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ToolDefinition(Protocol):
    """Immutable view over a catalog tool definition."""

    name: str
    phase: str
    languages: Sequence[str]

    def to_dict(self) -> Mapping[str, Any]:
        """Return a JSON-serialisable representation of the tool."""
        raise NotImplementedError


@runtime_checkable
class StrategyFactory(Protocol):
    """Factory callable responsible for building strategy instances."""

    def __call__(self, config: Mapping[str, Any] | None = None, /, **overrides: Any) -> Any:
        """Return a strategy object using catalogue-provided configuration."""
        raise NotImplementedError


@runtime_checkable
class CatalogSnapshot(Protocol):
    """Snapshot of the catalog containing tools, strategies, and metadata."""

    checksum: str

    @property
    def tools(self) -> Sequence[ToolDefinition]:  # pragma: no cover - Protocol property
        """Return the ordered collection of tools in the snapshot."""
        raise NotImplementedError

    def strategy(self, identifier: str) -> StrategyFactory:
        """Return the strategy factory registered under ``identifier``."""
        raise NotImplementedError
