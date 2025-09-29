"""I/O helpers for reading catalog JSON documents and schemas."""

from __future__ import annotations

import json
from pathlib import Path
from collections.abc import Mapping

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
    if not isinstance(payload, Mapping):
        raise CatalogIntegrityError(f"{path}: schema must be a JSON object at the root level")
    return payload


def load_document(path: Path) -> JSONValue:
    """Return a JSON document from *path*."""

    if not path.exists():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8") as stream:
        try:
            return json.load(stream)
        except json.JSONDecodeError as exc:  # pragma: no cover - json module provides rich context
            raise CatalogIntegrityError(f"{path}: failed to parse catalog JSON") from exc


__all__ = ["load_document", "load_schema"]
