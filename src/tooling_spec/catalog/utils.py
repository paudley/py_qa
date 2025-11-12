# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Utility helpers for validating and normalising catalog JSON structures."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from types import MappingProxyType

from .errors import CatalogIntegrityError
from .types import JSONValue


def expect_string(value: JSONValue | None, *, key: str, context: str) -> str:
    """Return ``value`` coerced to ``str`` or raise a catalog error.

    Args:
        value: Raw JSON value extracted from the catalog payload.
        key: Attribute name used in error messages.
        context: Human-friendly prefix describing the validation context.

    Returns:
        str: Value coerced to a string.

    Raises:
        CatalogIntegrityError: If ``value`` is not a string.
    """
    if not isinstance(value, str):
        raise CatalogIntegrityError(f"{context}: expected '{key}' to be a string")
    return value


def optional_string(value: JSONValue | None, *, key: str, context: str) -> str | None:
    """Return ``value`` as an optional string with validation.

    Args:
        value: Raw JSON value extracted from the catalog payload.
        key: Attribute name used in error messages.
        context: Human-friendly prefix describing the validation context.

    Returns:
        str | None: ``value`` coerced to ``str`` when present, otherwise ``None``.

    Raises:
        CatalogIntegrityError: If ``value`` is present but not a string.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        raise CatalogIntegrityError(f"{context}: expected '{key}' to be a string if present")
    return value


def optional_bool(
    value: JSONValue | None,
    *,
    key: str,
    context: str,
    default: bool | None = None,
) -> bool:
    """Return ``value`` coerced to ``bool`` with an optional default.

    Args:
        value: Raw JSON value extracted from the catalog payload.
        key: Attribute name used in error messages.
        context: Human-friendly prefix describing the validation context.
        default: Value returned when ``value`` is ``None``.

    Returns:
        bool: Boolean value derived from ``value`` or ``default``.

    Raises:
        CatalogIntegrityError: If ``value`` is not ``None`` and not a bool,
            or ``value`` is ``None`` and no ``default`` was provided.
    """
    if value is None:
        if default is None:
            raise CatalogIntegrityError(f"{context}: expected '{key}' to be a boolean")
        return default
    if isinstance(value, bool):
        return value
    raise CatalogIntegrityError(f"{context}: expected '{key}' to be a boolean")


def string_array(value: JSONValue | None, *, key: str, context: str) -> tuple[str, ...]:
    """Return ``value`` as a tuple of strings with validation.

    Args:
        value: Raw JSON value extracted from the catalog payload.
        key: Attribute name used in error messages.
        context: Human-friendly prefix describing the validation context.

    Returns:
        tuple[str, ...]: Tuple containing all string entries from ``value``.

    Raises:
        CatalogIntegrityError: If ``value`` is not a sequence of strings.
    """
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


def expect_mapping(value: JSONValue | None, *, key: str, context: str) -> Mapping[str, JSONValue]:
    """Return ``value`` as a mapping of JSON values or raise an error.

    Args:
        value: Raw JSON value extracted from the catalog payload.
        key: Attribute name used in error messages.
        context: Human-friendly prefix describing the validation context.

    Returns:
        Mapping[str, JSONValue]: Mapping derived from ``value``.

    Raises:
        CatalogIntegrityError: If ``value`` is not a mapping.
    """
    if not isinstance(value, Mapping):
        raise CatalogIntegrityError(f"{context}: expected '{key}' to be an object")
    return value


def freeze_json_mapping(value: Mapping[str, JSONValue], *, context: str) -> Mapping[str, JSONValue]:
    """Return an immutable mapping with recursively frozen JSON values.

    Args:
        value: Mapping to freeze.
        context: Human-friendly prefix describing the validation context.

    Returns:
        Mapping[str, JSONValue]: Mapping with recursively frozen entries.

    Raises:
        CatalogIntegrityError: If any key is not a string.
    """
    frozen: dict[str, JSONValue] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise CatalogIntegrityError(f"{context}: expected keys to be strings")
        frozen[key] = freeze_json_value(item, context=f"{context}.{key}")
    return MappingProxyType(frozen)


def freeze_json_value(value: JSONValue, *, context: str) -> JSONValue:
    """Return a recursively frozen view of ``value``.

    Args:
        value: JSON value to normalise.
        context: Human-friendly prefix describing the validation context.

    Returns:
        JSONValue: Frozen JSON value (mappings become mapping proxies, sequences tuples).

    Raises:
        CatalogIntegrityError: If ``value`` is not JSON compatible.
    """
    if isinstance(value, Mapping):
        return freeze_json_mapping(value, context=context)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(freeze_json_value(item, context=context) for item in value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise CatalogIntegrityError(f"{context}: unsupported JSON value type {type(value).__name__}")


def optional_number(value: JSONValue | None, *, key: str, context: str) -> float | None:
    """Return ``value`` as an optional float.

    Args:
        value: Raw JSON value extracted from the catalog payload.
        key: Attribute name used in error messages.
        context: Human-friendly prefix describing the validation context.

    Returns:
        float | None: Floating point representation of ``value`` or ``None``.

    Raises:
        CatalogIntegrityError: If ``value`` is present but not numeric.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    raise CatalogIntegrityError(f"{context}: expected '{key}' to be a number")


def string_mapping(value: JSONValue | None, *, key: str, context: str) -> Mapping[str, str]:
    """Return ``value`` as a mapping of strings.

    Args:
        value: Raw JSON value extracted from the catalog payload.
        key: Attribute name used in error messages.
        context: Human-friendly prefix describing the validation context.

    Returns:
        Mapping[str, str]: Mapping containing string keys and string values.

    Raises:
        CatalogIntegrityError: If ``value`` is not a mapping of strings.
    """
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


def thaw_json_value(value: JSONValue) -> JSONValue:
    """Return a plain JSON-compatible representation of ``value``.

    Args:
        value: Frozen JSON value that may contain mapping proxies or tuples.

    Returns:
        JSONValue: JSON-compatible value composed of built-in ``dict`` and
        ``list`` containers.
    """

    if isinstance(value, Mapping):
        return {str(key): thaw_json_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [thaw_json_value(item) for item in value]
    if isinstance(value, list):
        return [thaw_json_value(item) for item in value]
    return value


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
    "thaw_json_value",
]
