"""Catalog contracts for tool definitions and strategies."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable
from collections.abc import Mapping, Sequence


@runtime_checkable
class ToolDefinition(Protocol):
    """Immutable view over a catalog tool definition."""

    name: str
    phase: str
    languages: Sequence[str]

    def to_dict(self) -> Mapping[str, Any]:
        """Return a JSON-serialisable representation of the tool."""
        ...


@runtime_checkable
class StrategyFactory(Protocol):
    """Factory callable responsible for building strategy instances."""

    def __call__(self, **config: Any) -> Any:
        """Return a strategy object using catalogue-provided configuration."""
        ...


@runtime_checkable
class CatalogSnapshot(Protocol):
    """Snapshot of the catalog containing tools, strategies, and metadata."""

    checksum: str

    @property
    def tools(self) -> Sequence[ToolDefinition]:  # pragma: no cover - Protocol property
        """Return the ordered collection of tools in the snapshot."""
        ...

    def strategy(self, identifier: str) -> StrategyFactory:
        """Return the strategy factory registered under ``identifier``."""
        ...
