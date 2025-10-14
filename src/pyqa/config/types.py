# SPDX-License-Identifier: MIT
"""Shared typing utilities for configuration payloads."""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from typing import TYPE_CHECKING, TypeAlias

from pydantic.json_schema import JsonSchemaValue
from pydantic_core import core_schema

if TYPE_CHECKING:
    from tooling_spec.catalog.types import JSONValue as ConfigValue
else:

    class _ConfigJSON:
        """Runtime stand-in treated as ``any`` by Pydantic schema generation."""

        @classmethod
        def __get_pydantic_core_schema__(cls, _source, _handler) -> core_schema.CoreSchema:  # type: ignore[override]
            return core_schema.any_schema()

        @classmethod
        def __get_pydantic_json_schema__(cls, _core_schema, _handler) -> JsonSchemaValue:  # type: ignore[override]
            return {"type": "object"}

    ConfigValue = _ConfigJSON

ConfigPrimitive: TypeAlias = str | int | float | bool | None
ConfigFragment: TypeAlias = Mapping[str, ConfigValue]
MutableConfigFragment: TypeAlias = MutableMapping[str, ConfigValue]

__all__ = [
    "ConfigPrimitive",
    "ConfigValue",
    "ConfigFragment",
    "MutableConfigFragment",
]
