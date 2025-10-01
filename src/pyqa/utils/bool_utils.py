# SPDX-License-Identifier: MIT
"""Boolean parsing helpers shared across modules."""

from __future__ import annotations

from typing import Final

TRUTHY_LITERALS: Final[set[str]] = {"1", "true", "yes", "on"}
FALSY_LITERALS: Final[set[str]] = {"0", "false", "no", "off"}


def coerce_bool_literal(value: str) -> bool:
    """Return the boolean represented by ``value`` or raise ``ValueError``.

    Args:
        value: Raw string containing a boolean literal.

    Returns:
        bool: ``True`` for truthy literals, ``False`` for falsy literals.

    Raises:
        ValueError: If ``value`` does not match a known boolean literal.
    """

    normalized = value.strip().lower()
    if normalized in TRUTHY_LITERALS:
        return True
    if normalized in FALSY_LITERALS:
        return False
    raise ValueError(f"Unsupported boolean literal: {value!r}")


def interpret_optional_bool(value: object | None) -> bool | None:
    """Best-effort conversion of ``value`` into an optional boolean.

    ``None`` values remain ``None``; other types fall back to Python's truthiness
    rules when they are neither ``bool`` nor recognised string literals.

    Args:
        value: Value supplied by callers.

    Returns:
        bool | None: Parsed boolean or ``None`` when the input is unset.
    """

    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        try:
            return coerce_bool_literal(value)
        except ValueError:
            return bool(value)
    return bool(value)


__all__ = ["coerce_bool_literal", "interpret_optional_bool"]
