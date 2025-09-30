# SPDX-License-Identifier: MIT

# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Schema metadata describing supported tool-specific configuration keys."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache

from .catalog_metadata import CatalogOption, catalog_tool_options


@dataclass(frozen=True, slots=True)
class SettingField:
    """Structured representation of a tool configuration option."""

    type: str
    description: str
    enum: tuple[str, ...] | None = None

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serialisable representation of the setting field."""
        payload: dict[str, object] = {
            "type": self.type,
            "description": self.description,
        }
        if self.enum is not None:
            payload["enum"] = list(self.enum)
        return payload


ToolSettingSchema = Mapping[str, Mapping[str, SettingField]]
RawToolSettingSchema = dict[str, dict[str, dict[str, object]]]


def _normalise_type(option: CatalogOption) -> str:
    """Return the legacy type string for *option* based on catalog metadata."""
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
    """Create a :class:`SettingField` from a catalog option entry."""
    option_type = _normalise_type(option)
    enum = option.choices if option.choices else None
    return SettingField(
        type=option_type,
        description=option.description,
        enum=enum,
    )


@lru_cache(maxsize=1)
def _build_tool_setting_schema() -> OrderedDict[str, OrderedDict[str, SettingField]]:
    """Materialise the catalog-driven tool setting schema."""
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


TOOL_SETTING_SCHEMA: ToolSettingSchema = _build_tool_setting_schema()


def tool_setting_schema_as_dict() -> RawToolSettingSchema:
    """Return the tool setting schema as JSON-compatible dictionaries."""
    result: RawToolSettingSchema = {}
    for tool, fields in TOOL_SETTING_SCHEMA.items():
        result[tool] = {name: field.to_dict() for name, field in fields.items()}
    return result


__all__ = ["TOOL_SETTING_SCHEMA", "SettingField", "tool_setting_schema_as_dict"]
