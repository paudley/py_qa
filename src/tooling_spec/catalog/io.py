# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""I/O helpers for reading catalog JSON documents and schemas."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

from .errors import CatalogIntegrityError
from .types import JSONValue


def load_schema(path: Path) -> Mapping[str, JSONValue]:
    """Load a JSON schema from disk and ensure it is a JSON object.

    Args:
        path: Filesystem path to the schema file.

    Returns:
        Mapping[str, JSONValue]: Parsed JSON schema mapping.

    Raises:
        FileNotFoundError: If the schema file does not exist.
        CatalogIntegrityError: If the schema cannot be parsed or is not a JSON object.
    """
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8") as stream:
        try:
            payload = cast(JSONValue, json.load(stream))
        except json.JSONDecodeError as exc:  # pragma: no cover - json module provides rich context
            raise CatalogIntegrityError(f"{path}: failed to parse JSON schema") from exc
    mapping = _ensure_json_object(payload, context=str(path))
    return mapping


def load_document(path: Path) -> JSONValue:
    """Load a JSON document from disk and validate the payload.

    Args:
        path: Filesystem path to the JSON document.

    Returns:
        JSONValue: Parsed JSON value extracted from the document.

    Raises:
        FileNotFoundError: If the JSON document is missing.
        CatalogIntegrityError: If the document cannot be parsed or contains invalid JSON.
    """
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8") as stream:
        try:
            payload = cast(JSONValue, json.load(stream))
        except json.JSONDecodeError as exc:  # pragma: no cover - json module provides rich context
            raise CatalogIntegrityError(f"{path}: failed to parse catalog JSON") from exc
    return _ensure_json_value(payload, context=str(path))


__all__ = ["load_document", "load_schema"]


def _ensure_json_object(value: JSONValue, *, context: str) -> Mapping[str, JSONValue]:
    """Ensure ``value`` is a JSON object, raising on type mismatch.

    Args:
        value: Parsed JSON payload to validate.
        context: Human-readable context string used in error messages.

    Returns:
        Mapping[str, JSONValue]: Validated JSON object.

    Raises:
        CatalogIntegrityError: If ``value`` is not a mapping.
    """

    mapping = _ensure_json_value(value, context=context)
    if not isinstance(mapping, Mapping):
        raise CatalogIntegrityError(f"{context}: expected a JSON object")
    return mapping


def _ensure_json_value(value: JSONValue, *, context: str) -> JSONValue:
    """Ensure ``value`` is composed of JSON-compatible structures.

    Args:
        value: Parsed JSON payload to validate recursively.
        context: Human-readable context string used in error messages.

    Returns:
        JSONValue: Validated JSON value.

    Raises:
        CatalogIntegrityError: If ``value`` contains unsupported JSON constructs.
    """

    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _ensure_json_value(item, context=f"{context}.{key}") for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_ensure_json_value(item, context=f"{context}[]") for item in value]
    raise CatalogIntegrityError(f"{context}: value is not valid JSON")
