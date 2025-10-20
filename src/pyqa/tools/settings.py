# SPDX-License-Identifier: MIT

# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Schema metadata describing supported tool-specific configuration keys."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TypeAlias

from pyqa.cache import CacheProviderSettings, create_cache_provider
from pyqa.cache.in_memory import memoize
from pyqa.core.serialization import SerializableValue

from ..catalog.metadata import CatalogOption, catalog_tool_options

JSONPrimitive: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = JSONPrimitive | list["JSONValue"] | dict[str, "JSONValue"]


@dataclass(frozen=True, slots=True)
class SettingField:
    """Structured representation of a tool configuration option."""

    type: str
    description: str
    enum: tuple[str, ...] | None = None

    def to_dict(self) -> dict[str, JSONValue]:
        """Return a JSON-serialisable representation of the setting field.

        Returns:
            dict[str, JSONValue]: Mapping compatible with JSON serialization.
        """
        payload: dict[str, JSONValue] = {
            "type": self.type,
            "description": self.description,
        }
        if self.enum is not None:
            payload["enum"] = list(self.enum)
        return payload


ToolSettingSchema = Mapping[str, Mapping[str, SettingField]]
RawToolSettingSchema = dict[str, dict[str, dict[str, JSONValue]]]


def _normalise_type(option: CatalogOption) -> str:
    """Return the legacy type string for ``option`` based on catalog metadata.

    Args:
        option: Catalog option model describing the configuration field.

    Returns:
        str: Normalised legacy type label used by the CLI.
    """
    option_type = option.option_type.lower()
    alias_map = {
        "bool": "bool",
        "boolean": "bool",
        "int": "int",
        "integer": "int",
        "float": "float",
        "number": "float",
        "str": "str",
        "string": "str",
        "path": "path",
        "list[str]": "list[str]",
        "array": "list[str]",
    }
    return alias_map.get(option_type, option.option_type)


def _build_field(option: CatalogOption) -> SettingField:
    """Return a :class:`SettingField` constructed from a catalog option entry.

    Args:
        option: Catalog option metadata used to build the setting field.

    Returns:
        SettingField: Structured representation of the option.
    """
    option_type = _normalise_type(option)
    enum = option.choices if option.choices else None
    return SettingField(
        type=option_type,
        description=option.description,
        enum=enum,
    )


def _try_restore_schema(
    cached: SerializableValue | None,
) -> OrderedDict[str, OrderedDict[str, SettingField]] | None:
    """Return schema reconstructed from cached JSON-compatible data when possible.

    Args:
        cached: Cached value loaded from the cache provider.

    Returns:
        OrderedDict[str, OrderedDict[str, SettingField]] | None: Restored schema or ``None`` when
        restoration fails.
    """

    if not isinstance(cached, Mapping):
        return None
    reconstructed: OrderedDict[str, OrderedDict[str, SettingField]] = OrderedDict()
    for tool, raw_fields in cached.items():
        if not isinstance(raw_fields, Mapping):
            continue
        restored_fields: OrderedDict[str, SettingField] = OrderedDict()
        for name, definition in raw_fields.items():
            if not isinstance(definition, Mapping):
                continue
            enum_value = definition.get("enum")
            enum_tuple: tuple[str, ...] | None = None
            if isinstance(enum_value, Sequence) and not isinstance(enum_value, (str, bytes, bytearray)):
                enum_tuple = tuple(str(item) for item in enum_value)
            restored_fields[name] = SettingField(
                type=str(definition.get("type", "str")),
                description=str(definition.get("description", "")),
                enum=enum_tuple,
            )
        if restored_fields:
            reconstructed[tool] = restored_fields
    if reconstructed:
        return reconstructed
    return None


def _build_schema_from_catalog() -> OrderedDict[str, OrderedDict[str, SettingField]]:
    """Return schema constructed from the catalog metadata.

    Returns:
        OrderedDict[str, OrderedDict[str, SettingField]]: Schema keyed by tool name.
    """

    schema: OrderedDict[str, OrderedDict[str, SettingField]] = OrderedDict()
    options_map = catalog_tool_options()
    for tool_name in sorted(options_map):
        options = options_map[tool_name]
        if not options:
            continue
        field_map: OrderedDict[str, SettingField] = OrderedDict()
        for option in options:
            field_map[option.name] = _build_field(option)
        schema[tool_name] = field_map
    return schema


def _serialise_schema(schema: Mapping[str, Mapping[str, SettingField]]) -> RawToolSettingSchema:
    """Return a JSON-compatible representation of ``schema`` suitable for caching.

    Args:
        schema: Runtime schema mapping keyed by tool name.

    Returns:
        RawToolSettingSchema: JSON-friendly representation of the schema.
    """

    return {tool: {name: field.to_dict() for name, field in fields.items()} for tool, fields in schema.items()}


@memoize(maxsize=1)
def _schema_cache() -> ToolSettingSchema:
    """Return the cached tool setting schema keyed by tool name.

    Returns:
        ToolSettingSchema: Mapping from tool name to setting definitions.
    """

    provider = create_cache_provider(CacheProviderSettings(kind="memory"))
    cached = provider.get("tool-setting-schema")
    restored = _try_restore_schema(cached)
    if restored is not None:
        return restored

    schema = _build_schema_from_catalog()
    provider.set("tool-setting-schema", _serialise_schema(schema))
    return schema


TOOL_SETTING_SCHEMA: ToolSettingSchema = _schema_cache()


def tool_setting_schema_as_dict() -> RawToolSettingSchema:
    """Return the tool setting schema as JSON-compatible dictionaries.

    Returns:
        RawToolSettingSchema: Mapping from tool to serialisable field dictionaries.
    """
    result: RawToolSettingSchema = {}
    for tool, fields in TOOL_SETTING_SCHEMA.items():
        result[tool] = {name: field.to_dict() for name, field in fields.items()}
    return result


__all__ = ["TOOL_SETTING_SCHEMA", "SettingField", "tool_setting_schema_as_dict"]
