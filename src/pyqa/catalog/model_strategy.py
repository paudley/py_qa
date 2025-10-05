# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Strategy definition models for tooling catalog entries."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Final, Literal, TypeAlias

from .errors import CatalogIntegrityError
from .model_options import OptionType, normalize_option_type
from .types import STRATEGY_SCHEMA_VERSION, JSONValue
from .utils import expect_mapping, expect_string, optional_bool, optional_string

StrategyType: TypeAlias = Literal["command", "parser", "formatter", "postProcessor", "installer"]
_STRATEGY_TYPE_ALIASES: Final[dict[str, StrategyType]] = {
    "command": "command",
    "parser": "parser",
    "formatter": "formatter",
    "postprocessor": "postProcessor",
    "postProcessor": "postProcessor",
    "installer": "installer",
}


def normalize_strategy_type(value: JSONValue | None, *, context: str) -> StrategyType:
    """Return the canonical strategy type for catalog metadata.

    Args:
        value: JSON value that should contain the strategy type identifier.
        context: Human-readable context used in error messages.

    Returns:
        StrategyType: Canonicalised strategy type.

    Raises:
        CatalogIntegrityError: If the provided value is missing or unsupported.

    """

    raw = expect_string(value, key="type", context=context)
    alias = _STRATEGY_TYPE_ALIASES.get(raw)
    if alias is None:
        raise CatalogIntegrityError(f"{context}: unknown strategy type '{raw}'")
    return alias


@dataclass(frozen=True, slots=True)
class StrategyConfigField:
    """Metadata describing a configuration field consumed by a strategy."""

    value_type: OptionType
    required: bool
    description: str | None

    @staticmethod
    def from_mapping(data: Mapping[str, JSONValue], *, context: str) -> StrategyConfigField:
        """Create a configuration field descriptor from JSON data.

        Args:
            data: Mapping describing an individual configuration field.
            context: Human-readable context used in error messages.

        Returns:
            StrategyConfigField: Frozen descriptor for the configuration field.

        Raises:
            CatalogIntegrityError: If required field metadata is missing or invalid.

        """

        type_value = normalize_option_type(data.get("type"), context=context)
        required_value = optional_bool(
            data.get("required"),
            key="required",
            context=context,
            default=False,
        )
        description_value = optional_string(
            data.get("description"),
            key="description",
            context=context,
        )
        return StrategyConfigField(
            value_type=type_value,
            required=required_value,
            description=description_value,
        )


@dataclass(frozen=True, slots=True)
class StrategyMetadata:
    """Descriptive metadata about a strategy definition."""

    schema_version: str
    identifier: str
    strategy_type: StrategyType
    description: str | None


@dataclass(frozen=True, slots=True)
class StrategyImplementation:
    """Implementation details describing the strategy entry point."""

    module: str
    entry: str | None


@dataclass(frozen=True, slots=True)
class StrategyDefinition:
    """Immutable representation of a strategy catalog entry."""

    metadata: StrategyMetadata
    implementation_details: StrategyImplementation
    config: Mapping[str, StrategyConfigField]
    source: Path

    @property
    def schema_version(self) -> str:
        """Return the declared schema version for the strategy definition."""

        return self.metadata.schema_version

    @property
    def identifier(self) -> str:
        """Return the unique identifier for the strategy."""

        return self.metadata.identifier

    @property
    def strategy_type(self) -> StrategyType:
        """Return the strategy type describing runtime behaviour."""

        return self.metadata.strategy_type

    @property
    def description(self) -> str | None:
        """Return the optional human-readable description."""

        return self.metadata.description

    @property
    def implementation(self) -> str:
        """Return the module path implementing the strategy."""

        return self.implementation_details.module

    @property
    def entry(self) -> str | None:
        """Return the optional attribute referenced within the implementation module."""

        return self.implementation_details.entry

    @staticmethod
    def from_mapping(data: Mapping[str, JSONValue], *, source: Path) -> StrategyDefinition:
        """Create a ``StrategyDefinition`` from JSON data.

        Args:
            data: Mapping containing strategy configuration.
            source: Filesystem path to the JSON document providing the data.

        Returns:
            StrategyDefinition: Frozen strategy definition materialised from the mapping.

        Raises:
            CatalogIntegrityError: If the schema version or required fields are invalid.

        """

        context = str(source)
        metadata = parse_strategy_metadata(data, context=context)
        implementation = StrategyImplementation(
            module=expect_string(
                data.get("implementation"),
                key="implementation",
                context=context,
            ),
            entry=optional_string(data.get("entry"), key="entry", context=context),
        )
        config_value = strategy_config_mapping(
            data.get("config"),
            context=f"{context}.config",
        )
        return StrategyDefinition(
            metadata=metadata,
            implementation_details=implementation,
            config=config_value,
            source=source,
        )


def parse_strategy_metadata(
    data: Mapping[str, JSONValue],
    *,
    context: str,
) -> StrategyMetadata:
    """Return :class:`StrategyMetadata` parsed from the provided mapping."""

    schema_version_value = expect_string(
        data.get("schemaVersion"),
        key="schemaVersion",
        context=context,
    )
    if schema_version_value != STRATEGY_SCHEMA_VERSION:
        raise CatalogIntegrityError(
            f"{context}: schemaVersion '{schema_version_value}' is not supported; expected '{STRATEGY_SCHEMA_VERSION}'",
        )
    return StrategyMetadata(
        schema_version=schema_version_value,
        identifier=expect_string(data.get("id"), key="id", context=context),
        strategy_type=normalize_strategy_type(data.get("type"), context=context),
        description=optional_string(
            data.get("description"),
            key="description",
            context=context,
        ),
    )


def strategy_config_mapping(
    value: JSONValue | None,
    *,
    context: str,
) -> Mapping[str, StrategyConfigField]:
    """Return an immutable mapping of strategy configuration descriptors.

    Args:
        value: JSON value that should describe a mapping of configuration fields.
        context: Human-readable context used in error messages.

    Returns:
        Mapping[str, StrategyConfigField]: Immutable mapping of configuration descriptors.

    Raises:
        CatalogIntegrityError: If the value is not a mapping or the entries are invalid.

    """

    if value is None:
        return MappingProxyType({})
    if not isinstance(value, Mapping):
        raise CatalogIntegrityError(f"{context}: expected strategy config to be an object")
    frozen: dict[str, StrategyConfigField] = {}
    for field_name, field_value in value.items():
        if not isinstance(field_name, str):
            raise CatalogIntegrityError(f"{context}: expected strategy config keys to be strings")
        field_mapping = expect_mapping(field_value, key=field_name, context=context)
        frozen[field_name] = StrategyConfigField.from_mapping(
            field_mapping,
            context=f"{context}.{field_name}",
        )
    return MappingProxyType(frozen)


__all__ = [
    "StrategyConfigField",
    "StrategyDefinition",
    "StrategyImplementation",
    "StrategyMetadata",
    "StrategyType",
    "normalize_strategy_type",
    "parse_strategy_metadata",
    "strategy_config_mapping",
]
