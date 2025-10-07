# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Catalog contracts for tool definitions and strategies."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ToolDefinition(Protocol):
    """Immutable view over a catalog tool definition."""

    @property
    def name(self) -> str:
        """Return the stable tool identifier."""
        raise NotImplementedError("ToolDefinition.name must be implemented")

    @property
    def phase(self) -> str:
        """Return the execution phase associated with the tool."""
        raise NotImplementedError("ToolDefinition.phase must be implemented")

    @property
    def languages(self) -> Sequence[str]:
        """Return the languages supported by the tool."""
        raise NotImplementedError("ToolDefinition.languages must be implemented")

    def to_dict(self) -> Mapping[str, Any]:
        """Return a JSON-serialisable representation of the tool."""
        raise NotImplementedError


@runtime_checkable
class StrategyFactory(Protocol):
    """Factory callable responsible for building strategy instances."""

    @property
    def strategy_name(self) -> str:
        """Return the canonical name of the strategy."""
        raise NotImplementedError("StrategyFactory.strategy_name must be implemented")

    def __call__(self, config: Mapping[str, Any] | None = None, /, **overrides: Any) -> Any:
        """Return a strategy object using catalogue-provided configuration."""
        raise NotImplementedError


@runtime_checkable
class CatalogSnapshot(Protocol):
    """Snapshot of the catalog containing tools, strategies, and metadata."""

    @property
    def checksum(self) -> str:
        """Return the checksum that uniquely identifies this snapshot."""
        raise NotImplementedError("CatalogSnapshot.checksum must be implemented")

    @property
    def tools(self) -> Sequence[ToolDefinition]:
        """Return the ordered collection of tools in the snapshot."""
        raise NotImplementedError("CatalogSnapshot.tools must be implemented")

    def strategy(self, identifier: str) -> StrategyFactory:
        """Return the strategy factory registered under ``identifier``."""
        raise NotImplementedError
