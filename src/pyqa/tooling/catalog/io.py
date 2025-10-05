# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""I/O helpers for reading catalog JSON documents and schemas."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

from .errors import CatalogIntegrityError
from .types import JSONValue


def load_schema(path: Path) -> Mapping[str, JSONValue]:
    """Return a JSON schema from *path* ensuring it is a JSON object."""
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8") as stream:
        try:
            payload = json.load(stream)
        except json.JSONDecodeError as exc:  # pragma: no cover - json module provides rich context
            raise CatalogIntegrityError(f"{path}: failed to parse JSON schema") from exc
    mapping = _ensure_json_object(payload, context=str(path))
    return mapping


def load_document(path: Path) -> JSONValue:
    """Return a JSON document from *path*."""
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8") as stream:
        try:
            payload = json.load(stream)
        except json.JSONDecodeError as exc:  # pragma: no cover - json module provides rich context
            raise CatalogIntegrityError(f"{path}: failed to parse catalog JSON") from exc
    return _ensure_json_value(payload, context=str(path))


__all__ = ["load_document", "load_schema"]


def _ensure_json_object(value: object, *, context: str) -> Mapping[str, JSONValue]:
    mapping = _ensure_json_value(value, context=context)
    if not isinstance(mapping, Mapping):
        raise CatalogIntegrityError(f"{context}: expected a JSON object")
    return mapping


def _ensure_json_value(value: object, *, context: str) -> JSONValue:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _ensure_json_value(item, context=f"{context}.{key}") for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_ensure_json_value(item, context=f"{context}[]") for item in value]
    raise CatalogIntegrityError(f"{context}: value is not valid JSON")
