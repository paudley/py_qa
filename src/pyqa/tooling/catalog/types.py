"""Shared type aliases and constants for the tooling catalog."""

from __future__ import annotations

from typing import Final, Mapping, Sequence, TypeAlias

JSONPrimitive: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = JSONPrimitive | Sequence["JSONValue"] | Mapping[str, "JSONValue"]

TOOL_SCHEMA_VERSION: Final[str] = "1.0.0"
STRATEGY_SCHEMA_VERSION: Final[str] = "1.0.0"

__all__ = [
    "JSONPrimitive",
    "JSONValue",
    "TOOL_SCHEMA_VERSION",
    "STRATEGY_SCHEMA_VERSION",
]
