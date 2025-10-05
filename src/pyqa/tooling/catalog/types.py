# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Shared type aliases and constants for the tooling catalog."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final, TypeAlias

JSONPrimitive: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = JSONPrimitive | Sequence["JSONValue"] | Mapping[str, "JSONValue"]

TOOL_SCHEMA_VERSION: Final[str] = "1.0.0"
STRATEGY_SCHEMA_VERSION: Final[str] = "1.0.0"

__all__ = [
    "STRATEGY_SCHEMA_VERSION",
    "TOOL_SCHEMA_VERSION",
    "JSONPrimitive",
    "JSONValue",
]
