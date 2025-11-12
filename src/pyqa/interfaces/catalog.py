# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Catalog contracts for tool definitions and strategies."""

from __future__ import annotations

from abc import abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Protocol, runtime_checkable

from pyqa.core.serialization import JsonValue


@dataclass(frozen=True, slots=True)
class StrategyRequest:
    """Define a request object encapsulating configuration parameters for strategy factories.

    The request object provides a value object that merges layered configuration
    data with per-invocation overrides. Using a structured parameter object
    maintains SOLID semantics while avoiding variadic call signatures that
    complicate type checking and documentation.
    """

    base_config: Mapping[str, JsonValue] = field(default_factory=dict)
    overrides: Mapping[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Ensure mapping fields are converted into immutable proxies."""

        object.__setattr__(self, "base_config", MappingProxyType(dict(self.base_config)))
        object.__setattr__(self, "overrides", MappingProxyType(dict(self.overrides)))

    def merged_payload(self) -> Mapping[str, JsonValue]:
        """Return the merged configuration payload for strategy execution.

        Returns:
            Mapping[str, JsonValue]: Combined mapping where overrides win on key conflicts.
        """

        if not self.base_config and not self.overrides:
            return MappingProxyType({})
        merged: dict[str, JsonValue] = {}
        merged.update(self.base_config)
        merged.update(self.overrides)
        return MappingProxyType(merged)


@runtime_checkable
class ToolDefinition(Protocol):
    """Define an immutable view over a catalog tool definition."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the stable tool identifier.

        Returns:
            str: Identifier referencing the tool definition.
        """
        raise NotImplementedError("ToolDefinition.name must be implemented")

    @property
    @abstractmethod
    def phase(self) -> str:
        """Return the execution phase associated with the tool.

        Returns:
            str: Execution phase handled by the tool.
        """
        raise NotImplementedError("ToolDefinition.phase must be implemented")

    @property
    @abstractmethod
    def languages(self) -> Sequence[str]:
        """Return the languages supported by the tool.

        Returns:
            Sequence[str]: Language identifiers supported by the tool definition.
        """
        raise NotImplementedError("ToolDefinition.languages must be implemented")

    def to_dict(self) -> Mapping[str, JsonValue]:
        """Return a JSON-serialisable representation of the tool.

        Returns:
            Mapping[str, JsonValue]: JSON-compatible representation of the tool definition.
        """
        raise NotImplementedError("ToolDefinition.to_dict must be implemented")


@runtime_checkable
class StrategyFactory(Protocol):
    """Construct strategy instances from catalog configuration."""

    @property
    @abstractmethod
    def strategy_name(self) -> str:
        """Return the canonical name of the strategy.

        Returns:
            str: Identifier naming the catalog strategy implementation.
        """
        raise NotImplementedError("StrategyFactory.strategy_name must be implemented")

    def __call__(self, request: StrategyRequest) -> JsonValue | None:
        """Build a strategy using structured configuration parameters.

        Args:
            request: Structured request containing base configuration and overrides.

        Returns:
            JsonValue | None: Strategy descriptor or ``None`` when no strategy applies.
        """
        raise NotImplementedError("StrategyFactory.__call__ must be implemented")


@runtime_checkable
class CatalogSnapshot(Protocol):
    """Capture a catalog snapshot containing tools, strategies, and metadata."""

    @property
    @abstractmethod
    def checksum(self) -> str:
        """Return the checksum that uniquely identifies this snapshot.

        Returns:
            str: Checksum value representing the catalog snapshot.
        """
        raise NotImplementedError("CatalogSnapshot.checksum must be implemented")

    @property
    @abstractmethod
    def tools(self) -> Sequence[ToolDefinition]:
        """Return the ordered collection of tools in the snapshot.

        Returns:
            Sequence[ToolDefinition]: Ordered tool definitions known to the snapshot.
        """
        raise NotImplementedError("CatalogSnapshot.tools must be implemented")

    def strategy(self, identifier: str) -> StrategyFactory:
        """Return the strategy factory registered under ``identifier``.

        Args:
            identifier: Canonical strategy identifier to retrieve.

        Returns:
            StrategyFactory: Factory responsible for producing the strategy instance.
        """
        raise NotImplementedError("CatalogSnapshot.strategy must be implemented")


__all__ = [
    "CatalogSnapshot",
    "StrategyFactory",
    "StrategyRequest",
    "ToolDefinition",
]
