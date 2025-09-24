# SPDX-License-Identifier: MIT
"""Shared parser infrastructure and helper utilities."""

from __future__ import annotations

import json
from collections.abc import Mapping as MappingABC
from collections.abc import Sequence as SequenceABC
from dataclasses import dataclass
from typing import Any, Callable, Sequence

from ..models import RawDiagnostic
from ..tools.base import Parser, ToolContext

JsonTransform = Callable[[Any, ToolContext], Sequence[RawDiagnostic]]
TextTransform = Callable[[str, ToolContext], Sequence[RawDiagnostic]]


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
    if not isinstance(value, SequenceABC) or isinstance(value, (str, bytes, bytearray)):
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
        stdout: str,
        stderr: str,
        *,
        context: ToolContext,
    ) -> Sequence[RawDiagnostic]:
        del stderr  # retain signature compatibility without using the value
        payload = _load_json_stream(stdout)
        return self.transform(payload, context)


@dataclass(slots=True)
class TextParser(Parser):
    """Parse stdout via text transformation function."""

    transform: TextTransform

    def parse(
        self,
        stdout: str,
        stderr: str,
        *,
        context: ToolContext,
    ) -> Sequence[RawDiagnostic]:
        del stderr
        return self.transform(stdout, context)


__all__ = [
    "JsonParser",
    "TextParser",
    "JsonTransform",
    "TextTransform",
    "_load_json_stream",
    "_coerce_object_mapping",
    "_coerce_dict_sequence",
    "_coerce_optional_str",
]
