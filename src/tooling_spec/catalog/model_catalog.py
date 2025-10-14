# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Catalog aggregate models used by the tooling loader."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from .errors import CatalogIntegrityError
from .model_strategy import StrategyCallable, StrategyDefinition
from .model_tool import ToolDefinition
from .types import JSONValue


@dataclass(frozen=True, slots=True)
class CatalogFragment:
    """Shared catalog fragment intended for reuse across tool definitions."""

    name: str
    data: Mapping[str, JSONValue]
    source: Path


@dataclass(frozen=True, slots=True)
class CatalogSnapshot:
    """Materialised catalog data paired with a deterministic checksum."""

    _tools: tuple[ToolDefinition, ...]
    _strategies: tuple[StrategyDefinition, ...]
    _fragments: tuple[CatalogFragment, ...]
    checksum: str
    _strategy_factories: Mapping[str, StrategyCallable] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """Validate strategy identifiers and cache factory callables."""

        factories: dict[str, StrategyCallable] = {}
        for definition in self._strategies:
            identifier = definition.identifier
            if identifier in factories:
                raise CatalogIntegrityError(
                    f"Duplicate strategy identifier '{identifier}' detected in catalog snapshot",
                )
            factories[identifier] = definition.build_factory()
        object.__setattr__(self, "_strategy_factories", factories)

    @property
    def tools(self) -> tuple[ToolDefinition, ...]:
        """Return the tool definitions contained in the snapshot."""

        return self._tools

    @property
    def strategies(self) -> tuple[StrategyDefinition, ...]:
        """Return the strategy definitions contained in the snapshot."""

        return self._strategies

    @property
    def fragments(self) -> tuple[CatalogFragment, ...]:
        """Return fragment definitions available to catalog tools."""

        return self._fragments

    def strategy(self, identifier: str) -> StrategyCallable:
        """Return the strategy factory registered for ``identifier``.

        Args:
            identifier: Strategy identifier to resolve.

        Returns:
            StrategyCallable: Strategy factory callable referenced by ``identifier``.

        Raises:
            KeyError: If ``identifier`` is not known to the snapshot.
        """

        try:
            return self._strategy_factories[identifier]
        except KeyError as exc:  # pragma: no cover - defensive path
            raise KeyError(identifier) from exc


__all__ = [
    "CatalogFragment",
    "CatalogSnapshot",
]
