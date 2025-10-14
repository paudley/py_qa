# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Helpers for converting diagnostics and outcomes to serializable data."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from collections.abc import Set as AbstractSet
from pathlib import Path
from typing import Protocol, TypeAlias, runtime_checkable

from pydantic import BaseModel

from pyqa.core.models import (
    Diagnostic,
    JsonValue,
    ToolExitCategory,
    ToolOutcome,
    coerce_output_sequence,
)
from pyqa.core.severity import Severity


@runtime_checkable
class SupportsToDict(Protocol):
    """Protocol describing values that expose a ``to_dict`` JSON conversion hook."""

    def to_dict(self) -> SerializableValue:
        """Return an object that can be serialized via :func:`jsonify`."""


SerializableMapping: TypeAlias = dict[str, JsonValue]
SerializableValue: TypeAlias = (
    JsonValue
    | Path
    | BaseModel
    | Mapping[str, "SerializableValue"]
    | Sequence["SerializableValue"]
    | AbstractSet["SerializableValue"]
    | SupportsToDict
)


def serialize_diagnostic(diag: Diagnostic) -> SerializableMapping:
    """Convert a diagnostic into a JSON-friendly mapping."""
    return {
        "file": diag.file,
        "line": diag.line,
        "column": diag.column,
        "severity": diag.severity.value,
        "message": diag.message,
        "tool": diag.tool,
        "code": diag.code,
        "group": diag.group,
    }


def serialize_outcome(outcome: ToolOutcome) -> dict[str, JsonValue]:
    """Serialize a tool outcome including its diagnostics."""
    return {
        "tool": outcome.tool,
        "action": outcome.action,
        "returncode": outcome.returncode,
        "stdout": list(outcome.stdout),
        "stderr": list(outcome.stderr),
        "diagnostics": [serialize_diagnostic(diag) for diag in outcome.diagnostics],
        "cached": outcome.cached,
        "exit_category": outcome.exit_category.value,
    }


def deserialize_outcome(data: Mapping[str, JsonValue]) -> ToolOutcome:
    """Rehydrate a :class:`ToolOutcome` from the serialized representation."""
    diagnostics: list[Diagnostic] = []
    for entry in _coerce_diagnostic_payload(data.get("diagnostics")):
        severity_enum = _coerce_severity(entry.get("severity", "warning"))
        diagnostics.append(
            Diagnostic(
                file=coerce_optional_str(entry.get("file")),
                line=coerce_optional_int(entry.get("line")),
                column=coerce_optional_int(entry.get("column")),
                severity=severity_enum,
                message=str(entry.get("message", "")),
                tool=str(entry.get("tool", "")),
                code=coerce_optional_str(entry.get("code")),
                group=coerce_optional_str(entry.get("group")),
            ),
        )

    stdout_value = data.get("stdout", [])
    stderr_value = data.get("stderr", [])
    stdout_list = coerce_output_sequence(stdout_value)
    stderr_list = coerce_output_sequence(stderr_value)

    exit_category_raw = data.get("exit_category")
    exit_category = (
        _parse_exit_category(exit_category_raw) if isinstance(exit_category_raw, str) else ToolExitCategory.UNKNOWN
    )

    return ToolOutcome(
        tool=str(data.get("tool", "")),
        action=str(data.get("action", "")),
        returncode=safe_int(data.get("returncode")),
        stdout=stdout_list,
        stderr=stderr_list,
        diagnostics=diagnostics,
        cached=bool(data.get("cached", False)),
        exit_category=exit_category,
    )


def _parse_exit_category(value: str) -> ToolExitCategory:
    """Return a :class:`ToolExitCategory` derived from ``value`` with fallback."""

    try:
        return ToolExitCategory(value)
    except ValueError:
        return ToolExitCategory.UNKNOWN


def _coerce_severity(value: JsonValue) -> Severity:
    """Return a :class:`Severity` derived from ``value`` with fallback."""

    try:
        return Severity(str(value))
    except ValueError:
        return Severity.WARNING


def safe_int(value: JsonValue, default: int = 0) -> int:
    """Return ``value`` as ``int`` when possible, otherwise ``default``."""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def coerce_optional_int(value: JsonValue) -> int | None:
    """Return an optional integer parsed from ``value`` when feasible."""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def coerce_optional_str(value: JsonValue) -> str | None:
    """Return a string representation of ``value`` or ``None`` when unset."""
    if value is None:
        return None
    return str(value)


def _coerce_diagnostic_payload(value: JsonValue | Sequence[JsonValue] | None) -> list[SerializableMapping]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    diagnostics: list[SerializableMapping] = []
    for item in value:
        if isinstance(item, dict):
            diagnostics.append({str(key): val for key, val in item.items()})
    return diagnostics


def jsonify(value: SerializableValue) -> JsonValue:
    """Convert ``value`` into a JSON-compatible structure.

    Args:
        value: Value produced by runtime components that must be convertible into a
            JSON-compatible representation.

    Returns:
        JsonValue: Representation that can be serialized by JSON encoders.
    """

    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, BaseModel):
        model_payload = value.model_dump(mode="python", by_alias=True)
        return jsonify(model_payload)
    if isinstance(value, SupportsToDict):
        return jsonify(value.to_dict())
    if isinstance(value, Mapping):
        return {str(key): jsonify(item) for key, item in value.items()}
    if isinstance(value, AbstractSet):
        serialised = [jsonify(item) for item in value]
        try:
            return sorted(serialised, key=lambda item: json.dumps(item, sort_keys=True))
        except TypeError:
            return serialised
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [jsonify(item) for item in value]
    return str(value)


__all__ = [
    "coerce_optional_int",
    "coerce_optional_str",
    "deserialize_outcome",
    "JsonValue",
    "jsonify",
    "safe_int",
    "serialize_diagnostic",
    "serialize_outcome",
]
