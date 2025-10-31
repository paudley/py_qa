# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Shared typing utilities for configuration payloads."""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from typing import Annotated, TypeAlias

from pydantic import GetCoreSchemaHandler, GetJsonSchemaHandler
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import core_schema

from tooling_spec.catalog.types import JSONValue as _JSONValue


class _ConfigJSON:
    """Represent a permissive JSON sentinel understood by Pydantic."""

    __slots__ = ()

    @classmethod
    def __get_pydantic_core_schema__(
        cls,
        _source: type[_ConfigJSON],
        _handler: GetCoreSchemaHandler,
    ) -> core_schema.CoreSchema:
        """Construct a permissive core schema for configuration values.

        Args:
            _source: Source type provided by Pydantic during schema generation.
            _handler: Callback used to delegate schema construction when required.

        Returns:
            core_schema.CoreSchema: Schema describing unconstrained configuration values.
        """

        return core_schema.any_schema()

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        _core_schema: core_schema.CoreSchema,
        _handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        """Construct the JSON schema representing configuration values.

        Args:
            _core_schema: Core schema supplied by Pydantic.
            _handler: Callback used to resolve nested schema references.

        Returns:
            JsonSchemaValue: JSON-serialisable schema for documentation output.
        """

        return {"type": "object"}

    @classmethod
    def describe(cls) -> str:
        """Describe the semantics of the configuration value sentinel.

        Returns:
            str: Human-readable explanation of the sentinel usage.
        """

        return "Arbitrary JSON-compatible configuration fragment."

    @classmethod
    def example(cls) -> dict[str, str]:
        """Provide an illustrative configuration fragment for documentation.

        Returns:
            dict[str, str]: Minimal example fragment accepted by the sentinel.
        """

        return {}


ConfigPrimitive: TypeAlias = str | int | float | bool | None
ConfigValue: TypeAlias = Annotated[_JSONValue, _ConfigJSON]
ConfigFragment: TypeAlias = Mapping[str, ConfigValue]
MutableConfigFragment: TypeAlias = MutableMapping[str, ConfigValue]

__all__ = [
    "ConfigPrimitive",
    "ConfigValue",
    "ConfigFragment",
    "MutableConfigFragment",
]
