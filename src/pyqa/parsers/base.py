# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Shared parser infrastructure and helper utilities."""

from __future__ import annotations

import json
from collections.abc import Callable
from collections.abc import Mapping as MappingABC
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from ..models import RawDiagnostic
from ..tools.base import Parser, ToolContext

JsonTransform = Callable[[Any, ToolContext], Sequence[RawDiagnostic]]
TextTransform = Callable[[Sequence[str], ToolContext], Sequence[RawDiagnostic]]


def _ensure_lines(value: Sequence[str]) -> list[str]:
    """Normalise string-based output into a list of lines."""
    if isinstance(value, str):
        return value.splitlines()
    return [str(item) for item in value]


def _load_json_stream(stdout: str) -> Any:
    stdout = stdout.strip()
    if not stdout:
        return []
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        payload: list[Any] = []
        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                payload.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return payload


def _coerce_object_mapping(value: object) -> dict[str, object]:
    if isinstance(value, MappingABC):
        return {str(key): entry for key, entry in value.items()}
    return {}


def _coerce_dict_sequence(value: object) -> list[dict[str, object]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    collected: list[dict[str, object]] = []
    for item in value:
        if isinstance(item, MappingABC):
            collected.append(_coerce_object_mapping(item))
    return collected


def _coerce_optional_str(value: object | None) -> str | None:
    if isinstance(value, str):
        return value
    if value is None:
        return None
    return str(value)


@dataclass(slots=True)
class JsonParser(Parser):
    """Parse stdout as JSON and delegate to a transform function."""

    transform: JsonTransform

    def parse(
        self,
        stdout: Sequence[str],
        stderr: Sequence[str],
        *,
        context: ToolContext,
    ) -> Sequence[RawDiagnostic]:
        del stderr  # retain signature compatibility without using the value
        stdout_text = "\n".join(_ensure_lines(stdout))
        payload = _load_json_stream(stdout_text)
        return self.transform(payload, context)


@dataclass(slots=True)
class TextParser(Parser):
    """Parse stdout via text transformation function."""

    transform: TextTransform

    def parse(
        self,
        stdout: Sequence[str],
        stderr: Sequence[str],
        *,
        context: ToolContext,
    ) -> Sequence[RawDiagnostic]:
        del stderr
        lines = _ensure_lines(stdout)
        return self.transform(lines, context)


__all__ = [
    "JsonParser",
    "JsonTransform",
    "TextParser",
    "TextTransform",
    "_coerce_dict_sequence",
    "_coerce_object_mapping",
    "_coerce_optional_str",
    "_ensure_lines",
    "_load_json_stream",
]
