# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Shared serialization protocols and type aliases."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from collections.abc import Set as AbstractSet
from pathlib import Path
from typing import Protocol, TypeAlias, runtime_checkable

from pydantic import BaseModel

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]


@runtime_checkable
class SupportsToDict(Protocol):
    """Protocol describing objects that expose a :meth:`to_dict` hook."""

    def to_dict(self) -> SerializableValue:
        """Return a JSON-compatible representation of the object.

        Returns:
            SerializableValue: JSON-compatible representation of the object.
        """

    def __call__(self) -> SerializableValue:
        """Return :meth:`to_dict` to support call-style usage.

        Returns:
            SerializableValue: JSON-compatible representation of the object.
        """

        return self.to_dict()


SerializableValue: TypeAlias = (
    JsonValue
    | Path
    | BaseModel
    | Mapping[str, "SerializableValue"]
    | Sequence["SerializableValue"]
    | AbstractSet["SerializableValue"]
    | SupportsToDict
)
SerializableMapping: TypeAlias = dict[str, JsonValue]
