# SPDX-License-Identifier: MIT
"""Strategy reference helpers for catalog-backed actions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from .types import JSONValue
from .utils import expect_mapping, expect_string, freeze_json_mapping


@dataclass(frozen=True, slots=True)
class StrategyReference:
    """Reference to a reusable strategy defined in the strategy catalog."""

    strategy: str
    config: Mapping[str, JSONValue]

    @staticmethod
    def from_mapping(data: Mapping[str, JSONValue], *, context: str) -> StrategyReference:
        """Create a ``StrategyReference`` instance from JSON data.

        Args:
            data: Mapping that describes the strategy reference.
            context: Human-readable context used in error messages.

        Returns:
            StrategyReference: Frozen representation of the strategy reference.

        Raises:
            CatalogIntegrityError: If required keys are missing or invalid.

        """

        strategy_value = expect_string(data.get("strategy"), key="strategy", context=context)
        config_data = data.get("config")
        config_mapping = (
            freeze_json_mapping(
                expect_mapping(config_data, key="config", context=context),
                context=f"{context}.config",
            )
            if isinstance(config_data, Mapping)
            else MappingProxyType({})
        )
        return StrategyReference(strategy=strategy_value, config=config_mapping)


@dataclass(frozen=True, slots=True)
class CommandDefinition:
    """Strategy-backed command definition bound to a tool action."""

    reference: StrategyReference

    @staticmethod
    def from_mapping(data: Mapping[str, JSONValue], *, context: str) -> CommandDefinition:
        """Create a ``CommandDefinition`` from JSON data.

        Args:
            data: Mapping containing command configuration.
            context: Human-readable context used in error messages.

        Returns:
            CommandDefinition: Frozen command definition.

        Raises:
            CatalogIntegrityError: If the mapping cannot be converted to a command reference.

        """

        return CommandDefinition(reference=StrategyReference.from_mapping(data, context=context))


@dataclass(frozen=True, slots=True)
class ParserDefinition:
    """Strategy-backed parser definition bound to a tool action."""

    reference: StrategyReference

    @staticmethod
    def from_mapping(data: Mapping[str, JSONValue], *, context: str) -> ParserDefinition:
        """Create a ``ParserDefinition`` from JSON data.

        Args:
            data: Mapping containing parser configuration.
            context: Human-readable context used in error messages.

        Returns:
            ParserDefinition: Frozen parser definition.

        Raises:
            CatalogIntegrityError: If the mapping cannot be converted to a parser reference.

        """

        return ParserDefinition(reference=StrategyReference.from_mapping(data, context=context))


__all__ = [
    "CommandDefinition",
    "ParserDefinition",
    "StrategyReference",
]
