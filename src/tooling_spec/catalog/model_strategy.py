# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Strategy definition models for tooling catalog entries."""

from __future__ import annotations

import importlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final, Literal, TypeAlias, cast

from .errors import CatalogIntegrityError
from .model_options import OptionType, normalize_option_type
from .types import STRATEGY_SCHEMA_VERSION, JSONValue
from .utils import (
    expect_mapping,
    expect_string,
    freeze_json_mapping,
    optional_bool,
    optional_string,
    thaw_json_value,
)

StrategyType: TypeAlias = Literal["command", "parser", "formatter", "postProcessor", "installer"]
_STRATEGY_TYPE_ALIASES: Final[dict[str, StrategyType]] = {
    "command": "command",
    "parser": "parser",
    "formatter": "formatter",
    "postprocessor": "postProcessor",
    "postProcessor": "postProcessor",
    "installer": "installer",
}


@dataclass(slots=True)
class _StrategyFactory:
    """Callable wrapper that normalises payloads for strategy implementations."""

    implementation: Callable[..., Any]

    def __call__(self, config: Mapping[str, Any] | None = None, **overrides: Any) -> Any:
        """Invoke ``implementation`` with a merged mapping of configuration values.

        Args:
            config: Optional mapping sourced from catalog metadata.
            **overrides: Keyword overrides supplied by runtime callers.

        Returns:
            Any: Result produced by the underlying strategy implementation.
        """

        payload: dict[str, Any] = {}
        if config is not None:
            payload.update({str(key): value for key, value in config.items()})
        if overrides:
            payload.update(overrides)
        try:
            return self.implementation(payload)
        except TypeError:
            if payload:
                raise
            return self.implementation()


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
    _raw_mapping: Mapping[str, JSONValue] = field(repr=False, compare=False)

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

    def to_dict(self) -> Mapping[str, JSONValue]:
        """Return a JSON-compatible representation of the strategy definition.

        Returns:
            Mapping[str, JSONValue]: Mapping mirroring the catalog strategy
            document that produced the definition.
        """

        return cast(Mapping[str, JSONValue], thaw_json_value(self._raw_mapping))

    def resolve_callable(self) -> Callable[..., Any]:
        """Return the callable implementing the strategy.

        Returns:
            Callable[..., Any]: Imported callable referenced by the strategy
            metadata.

        Raises:
            CatalogIntegrityError: If the implementation cannot be imported or
            does not reference a callable attribute.
        """

        if self.entry is not None:
            try:
                module = importlib.import_module(self.implementation)
            except ImportError as exc:
                raise CatalogIntegrityError(
                    f"{self.source}: unable to import strategy module '{self.implementation}'",
                ) from exc
            attribute = getattr(module, self.entry, None)
            if attribute is None:
                raise CatalogIntegrityError(
                    f"{self.source}: module '{self.implementation}' has no attribute '{self.entry}'",
                )
        else:
            module_path, _, attribute_name = self.implementation.rpartition(".")
            if not module_path:
                raise CatalogIntegrityError(
                    f"{self.source}: implementation '{self.implementation}' must include a module path",
                )
            try:
                module = importlib.import_module(module_path)
            except ImportError as exc:
                raise CatalogIntegrityError(
                    f"{self.source}: unable to import strategy module '{module_path}'",
                ) from exc
            attribute = getattr(module, attribute_name, None)
            if attribute is None:
                raise CatalogIntegrityError(
                    f"{self.source}: module '{module_path}' has no attribute '{attribute_name}'",
                )

        if not callable(attribute):
            raise CatalogIntegrityError(
                f"{self.source}: strategy implementation '{self.implementation}' is not callable",
            )
        return cast(Callable[..., Any], attribute)

    def build_factory(self) -> Callable[..., Any]:
        """Return a factory that executes the underlying strategy callable.

        Returns:
            Callable[[Mapping[str, Any] | None], Any]: Factory callable that
            accepts an optional configuration mapping and delegates to the
            imported implementation.
        """

        implementation = self.resolve_callable()
        return _StrategyFactory(implementation=implementation)

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
        mapping = expect_mapping(data, key="<root>", context=context)
        frozen_mapping = freeze_json_mapping(mapping, context=context)

        metadata = parse_strategy_metadata(mapping, context=context)
        implementation = StrategyImplementation(
            module=expect_string(
                mapping.get("implementation"),
                key="implementation",
                context=context,
            ),
            entry=optional_string(mapping.get("entry"), key="entry", context=context),
        )
        config_value = strategy_config_mapping(
            mapping.get("config"),
            context=f"{context}.config",
        )
        return StrategyDefinition(
            metadata=metadata,
            implementation_details=implementation,
            config=config_value,
            source=source,
            _raw_mapping=frozen_mapping,
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


__all__: Final[tuple[str, ...]] = (
    "StrategyConfigField",
    "StrategyDefinition",
    "StrategyImplementation",
    "StrategyMetadata",
    "StrategyType",
    "normalize_strategy_type",
    "parse_strategy_metadata",
    "strategy_config_mapping",
)
