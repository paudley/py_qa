"""Fragment resolution helpers for catalog documents."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import cast

from .errors import CatalogIntegrityError
from .models import CatalogFragment
from .types import JSONValue
from .utils import freeze_json_value, string_array


def resolve_tool_mapping(
    mapping: Mapping[str, JSONValue],
    *,
    context: str,
    fragments: Mapping[str, CatalogFragment],
) -> Mapping[str, JSONValue]:
    """Apply fragment extensions declared by a tool definition.

    Args:
        mapping: Raw mapping loaded from the tool JSON document.
        context: Context string incorporating the source path for error reporting.
        fragments: Mapping of fragment identifiers to their catalog definitions.

    Returns:
        Mapping[str, JSONValue]: Tool mapping with fragment data merged and ``extends`` removed.

    Raises:
        CatalogIntegrityError: If the tool references unknown fragments or repeats identifiers.

    """
    extends_value = mapping.get("extends")
    merged: Mapping[str, JSONValue] = MappingProxyType({})
    if extends_value is not None:
        fragment_names = string_array(extends_value, key="extends", context=context)
        seen: set[str] = set()
        for identifier in fragment_names:
            if identifier in seen:
                raise CatalogIntegrityError(
                    f"{context}: fragment '{identifier}' referenced multiple times in extends",
                )
            seen.add(identifier)
            fragment = fragments.get(identifier)
            if fragment is None:
                raise CatalogIntegrityError(
                    f"{context}: unknown fragment '{identifier}' referenced in extends",
                )
            merged = merge_json_objects(
                merged,
                fragment.data,
                context=f"{context}.extends[{identifier}]",
            )

    overlay = {key: value for key, value in mapping.items() if key != "extends"}
    return merge_json_objects(merged, overlay, context=context)


def merge_json_objects(
    base: Mapping[str, JSONValue],
    overlay: Mapping[str, JSONValue],
    *,
    context: str,
) -> Mapping[str, JSONValue]:
    """Recursively merge JSON mappings without mutating inputs.

    Args:
        base: Base JSON mapping.
        overlay: Mapping whose values override or extend *base*.
        context: Context string incorporating the source path for error reporting.

    Returns:
        Mapping[str, JSONValue]: Frozen mapping representing the merged result.

    """
    merged: dict[str, JSONValue] = {}
    for key, value in base.items():
        merged[key] = freeze_json_value(value, context=f"{context}.{key}")
    for key, value in overlay.items():
        if key in merged and isinstance(merged[key], Mapping) and isinstance(value, Mapping):
            merged[key] = merge_json_objects(
                cast("Mapping[str, JSONValue]", merged[key]),
                cast("Mapping[str, JSONValue]", value),
                context=f"{context}.{key}",
            )
        else:
            frozen_value = freeze_json_value(value, context=f"{context}.{key}")
            existing = merged.get(key)
            if isinstance(existing, tuple) and isinstance(frozen_value, tuple):
                merged[key] = tuple(dict.fromkeys(existing + frozen_value))
            else:
                merged[key] = frozen_value
    return MappingProxyType(merged)


def to_plain_json(value: JSONValue) -> JSONValue:
    """Convert frozen JSON structures into mutable equivalents for schema validation."""
    if isinstance(value, Mapping):
        return {key: to_plain_json(cast("JSONValue", item)) for key, item in value.items()}
    if isinstance(value, tuple):
        return [to_plain_json(cast("JSONValue", item)) for item in value]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [to_plain_json(cast("JSONValue", item)) for item in value]
    return value


__all__ = ["merge_json_objects", "resolve_tool_mapping", "to_plain_json"]
