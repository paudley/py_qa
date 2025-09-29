"""Utility helpers for validating and normalising catalog JSON structures."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from types import MappingProxyType

from .errors import CatalogIntegrityError
from .types import JSONValue


def expect_string(value: object | None, *, key: str, context: str) -> str:
    """Return *value* as a string or raise :class:`CatalogIntegrityError`."""
    if not isinstance(value, str):
        raise CatalogIntegrityError(f"{context}: expected '{key}' to be a string")
    return value


def optional_string(value: object | None, *, key: str, context: str) -> str | None:
    """Return *value* as an optional string with validation."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise CatalogIntegrityError(f"{context}: expected '{key}' to be a string if present")
    return value


def optional_bool(
    value: object | None,
    *,
    key: str,
    context: str,
    default: bool | None = None,
) -> bool:
    """Return *value* as a boolean with optional default handling."""
    if value is None:
        if default is None:
            raise CatalogIntegrityError(f"{context}: expected '{key}' to be a boolean")
        return default
    if isinstance(value, bool):
        return value
    raise CatalogIntegrityError(f"{context}: expected '{key}' to be a boolean")


def string_array(value: object | None, *, key: str, context: str) -> tuple[str, ...]:
    """Return *value* as a tuple of strings with validation."""
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise CatalogIntegrityError(f"{context}: expected '{key}' to be an array of strings")
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str):
            raise CatalogIntegrityError(f"{context}: expected '{key}[{index}]' to be a string")
        result.append(item)
    return tuple(result)


def expect_mapping(value: object | None, *, key: str, context: str) -> Mapping[str, JSONValue]:
    """Return *value* as a mapping of JSON values or raise an integrity error."""
    if not isinstance(value, Mapping):
        raise CatalogIntegrityError(f"{context}: expected '{key}' to be an object")
    return value


def freeze_json_mapping(value: Mapping[str, JSONValue], *, context: str) -> Mapping[str, JSONValue]:
    """Return an immutable mapping with recursively frozen JSON values."""
    frozen: dict[str, JSONValue] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise CatalogIntegrityError(f"{context}: expected keys to be strings")
        frozen[key] = freeze_json_value(item, context=f"{context}.{key}")
    return MappingProxyType(frozen)


def freeze_json_value(value: JSONValue, *, context: str) -> JSONValue:
    """Return an immutable JSON value."""
    if isinstance(value, Mapping):
        return freeze_json_mapping(value, context=context)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(freeze_json_value(item, context=context) for item in value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise CatalogIntegrityError(f"{context}: unsupported JSON value type {type(value).__name__}")


def optional_number(value: object | None, *, key: str, context: str) -> float | None:
    """Return *value* as an optional float."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    raise CatalogIntegrityError(f"{context}: expected '{key}' to be a number")


def string_mapping(value: object | None, *, key: str, context: str) -> Mapping[str, str]:
    """Return *value* as a mapping of strings."""
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise CatalogIntegrityError(f"{context}: expected '{key}' to be an object")
    result: dict[str, str] = {}
    for item_key, item_value in value.items():
        if not isinstance(item_key, str) or not isinstance(item_value, str):
            raise CatalogIntegrityError(f"{context}: expected '{key}' to be a mapping of strings")
        result[item_key] = item_value
    return result


__all__ = [
    "expect_mapping",
    "expect_string",
    "freeze_json_mapping",
    "freeze_json_value",
    "optional_bool",
    "optional_number",
    "optional_string",
    "string_array",
    "string_mapping",
]
