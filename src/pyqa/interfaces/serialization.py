# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Shared serialization protocols and type declarations."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from collections.abc import Set as AbstractSet
from pathlib import Path
from typing import Protocol, runtime_checkable

from pyqa.interfaces.core import JsonValue

type SerializableMapping = Mapping[str, JsonValue]


@runtime_checkable
class SupportsToDict(Protocol):
    """Protocol describing objects that expose a :meth:`to_dict` hook."""

    def to_dict(self) -> SerializableMapping:
        """Return a JSON-compatible representation of the object.

        Returns:
            SerializableMapping: JSON-safe payload describing the object.
        """
        ...

    def __call__(self) -> SerializableMapping:
        """Return :meth:`to_dict` to support call-style usage.

        Returns:
            SerializableMapping: Alias for :meth:`to_dict`.
        """
        ...


@runtime_checkable
class SupportsModelDump(Protocol):
    """Protocol describing objects that support :meth:`model_dump` (e.g. Pydantic models)."""

    def model_dump(self, *, mode: str = "python", by_alias: bool = False) -> SerializableMapping:
        """Return a mapping suitable for JSON serialization.

        Args:
            mode: Output mode requested by the caller (defaults to ``python``).
            by_alias: Flag indicating whether alias names should be used.

        Returns:
            SerializableMapping: Serialized payload emitted by the model.
        """
        ...


type SerializableValue = (
    JsonValue
    | Path
    | Mapping[str, "SerializableValue"]
    | Sequence["SerializableValue"]
    | AbstractSet["SerializableValue"]
    | SupportsToDict
    | SupportsModelDump
)


__all__ = [
    "SerializableMapping",
    "SerializableValue",
    "SupportsModelDump",
    "SupportsToDict",
]
