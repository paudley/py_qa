# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Helpers for converting diagnostics and outcomes to serializable data."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from collections.abc import Set as AbstractSet
from pathlib import Path
from typing import Any, TypeAlias

from pydantic import BaseModel

from .models import Diagnostic, ToolOutcome, coerce_output_sequence
from .severity import Severity

JsonPrimitive: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonPrimitive | list["JsonValue"] | dict[str, "JsonValue"]


def serialize_diagnostic(diag: Diagnostic) -> dict[str, object | None]:
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


def serialize_outcome(outcome: ToolOutcome) -> dict[str, object]:
    """Serialize a tool outcome including its diagnostics."""
    return {
        "tool": outcome.tool,
        "action": outcome.action,
        "returncode": outcome.returncode,
        "stdout": list(outcome.stdout),
        "stderr": list(outcome.stderr),
        "diagnostics": [serialize_diagnostic(diag) for diag in outcome.diagnostics],
        "cached": outcome.cached,
    }


def deserialize_outcome(data: Mapping[str, Any]) -> ToolOutcome:
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

    return ToolOutcome(
        tool=str(data.get("tool", "")),
        action=str(data.get("action", "")),
        returncode=safe_int(data.get("returncode")),
        stdout=stdout_list,
        stderr=stderr_list,
        diagnostics=diagnostics,
        cached=bool(data.get("cached", False)),
    )


def _coerce_severity(value: object) -> Severity:
    """Return a :class:`Severity` derived from ``value`` with fallback."""

    try:
        return Severity(str(value))
    except ValueError:
        return Severity.WARNING


def safe_int(value: object, default: int = 0) -> int:
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


def coerce_optional_int(value: object) -> int | None:
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


def coerce_optional_str(value: object) -> str | None:
    """Return a string representation of ``value`` or ``None`` when unset."""
    if value is None:
        return None
    return str(value)


def _coerce_diagnostic_payload(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    diagnostics: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, dict):
            diagnostics.append(item)
    return diagnostics


def jsonify(value: Any) -> JsonValue:
    """Convert ``value`` into a JSON-serializable payload."""
    if isinstance(value, (str, int, float, bool)) or value is None:
        result: JsonValue = value
    elif isinstance(value, Path):
        result = str(value)
    elif isinstance(value, BaseModel):
        result = jsonify(value.model_dump(mode="python", by_alias=True))
    elif hasattr(value, "to_dict"):
        dumped = value.to_dict()  # type: ignore[call-arg, no-untyped-call]
        result = jsonify(dumped)
    elif isinstance(value, Mapping):
        result = {str(key): jsonify(item) for key, item in value.items()}
    elif isinstance(value, AbstractSet):
        serialised = [jsonify(item) for item in value]
        try:
            result = sorted(serialised, key=lambda item: json.dumps(item, sort_keys=True))
        except TypeError:
            result = serialised
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        result = [jsonify(item) for item in value]
    else:
        result = str(value)
    return result


__all__ = [
    "coerce_optional_int",
    "coerce_optional_str",
    "deserialize_outcome",
    "jsonify",
    "safe_int",
    "serialize_diagnostic",
    "serialize_outcome",
]
