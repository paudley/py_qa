# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Shared parser infrastructure and helper utilities."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterator
from collections.abc import Mapping as MappingABC
from collections.abc import Sequence
from dataclasses import dataclass
from typing import cast

from pyqa.core.serialization import JsonValue
from pyqa.core.severity import Severity

from ..core.models import RawDiagnostic
from ..tools.base import Parser, ToolContext

JsonTransform = Callable[[JsonValue, ToolContext], Sequence[RawDiagnostic]]
TextTransform = Callable[[Sequence[str], ToolContext], Sequence[RawDiagnostic]]


def _ensure_lines(value: Sequence[str]) -> list[str]:
    """Normalise string-based output into a list of lines."""
    if isinstance(value, str):
        return value.splitlines()
    return [str(item) for item in value]


def _load_json_stream(stdout: str) -> JsonValue:
    stdout = stdout.strip()
    if not stdout:
        return []
    try:
        return cast(JsonValue, json.loads(stdout))
    except json.JSONDecodeError:
        payload: list[JsonValue] = []
        for raw_line in stdout.splitlines():
            trimmed = raw_line.strip()
            if not trimmed:
                continue
            try:
                payload.append(cast(JsonValue, json.loads(trimmed)))
            except json.JSONDecodeError:
                continue
        return payload


def _coerce_object_mapping(value: JsonValue) -> dict[str, JsonValue]:
    if isinstance(value, MappingABC):
        return {str(key): cast(JsonValue, entry) for key, entry in value.items()}
    return {}


def _coerce_dict_sequence(value: JsonValue) -> list[dict[str, JsonValue]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    collected: list[dict[str, JsonValue]] = []
    for item in value:
        if isinstance(item, MappingABC):
            collected.append(_coerce_object_mapping(item))
    return collected


def _coerce_optional_str(value: JsonValue | None) -> str | None:
    if isinstance(value, str):
        return value
    if value is None:
        return None
    return str(value)


def iter_dicts(value: JsonValue) -> Iterator[MappingABC[str, JsonValue]]:
    """Yield mapping items from ``value`` when it is a sequence of dict-like objects."""

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in value:
            if isinstance(item, MappingABC):
                yield item


def map_severity(label: JsonValue, mapping: MappingABC[str, Severity], default: Severity) -> Severity:
    """Return a :class:`Severity` derived from ``label`` using ``mapping``."""

    if isinstance(label, str):
        return mapping.get(label.lower(), default)
    return default


@dataclass(slots=True)
class DiagnosticLocation:
    """Describe the file and position associated with a diagnostic."""

    file: str | None
    line: int | None
    column: int | None


@dataclass(slots=True)
class DiagnosticDetails:
    """Capture diagnostic metadata excluding the physical location."""

    severity: Severity
    message: str
    tool: str
    code: str | None = None
    function: str | None = None


@dataclass(slots=True)
class RawDiagnosticSpec:
    """Group the parameters required to build a :class:`RawDiagnostic`."""

    location: DiagnosticLocation
    details: DiagnosticDetails

    def build(self) -> RawDiagnostic:
        """Materialise the spec as a :class:`RawDiagnostic` instance."""

        return RawDiagnostic(
            file=self.location.file,
            line=self.location.line,
            column=self.location.column,
            severity=self.details.severity,
            message=self.details.message,
            code=self.details.code,
            tool=self.details.tool,
            function=self.details.function,
        )


def create_spec(
    *,
    location: DiagnosticLocation,
    details: DiagnosticDetails,
) -> RawDiagnosticSpec:
    """Create a diagnostic spec encapsulating location and metadata.

    Args:
        location: File and positional information describing the diagnostic.
        details: Metadata collected from the originating tool.

    Returns:
        RawDiagnosticSpec: Deferred diagnostic instance ready for construction.
    """

    return RawDiagnosticSpec(
        location=location,
        details=details,
    )


def append_raw_diagnostic(collection: list[RawDiagnostic], *, spec: RawDiagnosticSpec) -> None:
    """Append ``spec`` to ``collection`` after converting it to :class:`RawDiagnostic`.

    Args:
        collection: Mutable sequence receiving the materialised diagnostic.
        spec: Deferred diagnostic representation awaiting conversion.
    """

    collection.append(build_raw_diagnostic(spec))


def append_diagnostic(
    collection: list[RawDiagnostic],
    *,
    location: DiagnosticLocation,
    details: DiagnosticDetails,
) -> None:
    """Build a :class:`RawDiagnostic` from provided details and append to ``collection``.

    Args:
        collection: Target list receiving the diagnostic instance.
        location: File system location describing where the issue occurs.
        details: Metadata describing the diagnostic produced by a tool.
    """

    append_raw_diagnostic(collection, spec=create_spec(location=location, details=details))


def build_raw_diagnostic(spec: RawDiagnosticSpec) -> RawDiagnostic:
    """Return a :class:`RawDiagnostic` created from *spec*.

    Args:
        spec: Grouped diagnostic attributes describing the target warning.

    Returns:
        RawDiagnostic: Normalised diagnostic built from ``spec``.
    """

    return spec.build()


def iter_pattern_matches(
    lines: Sequence[str],
    pattern: re.Pattern[str],
    *,
    skip_prefixes: Sequence[str] = (),
    skip_blank: bool = True,
) -> Iterator[re.Match[str]]:
    """Yield regex matches from ``lines`` while filtering unwanted entries.

    Args:
        lines: Sequence of raw lines emitted by a tool.
        pattern: Compiled regular expression used to match diagnostic lines.
        skip_prefixes: Optional prefixes that, when present, skip the line.
        skip_blank: When ``True`` blank lines are ignored.

    Yields:
        re.Match[str]: Match objects produced by ``pattern``.
    """

    forbidden = tuple(skip_prefixes)
    for raw_line in lines:
        line = raw_line.strip()
        if skip_blank and not line:
            continue
        if forbidden and any(line.startswith(prefix) for prefix in forbidden):
            continue
        match = pattern.match(line)
        if match:
            yield match


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
    "DiagnosticDetails",
    "DiagnosticLocation",
    "RawDiagnosticSpec",
    "append_diagnostic",
    "append_raw_diagnostic",
    "build_raw_diagnostic",
    "create_spec",
    "JsonParser",
    "JsonTransform",
    "TextParser",
    "TextTransform",
    "iter_dicts",
    "iter_pattern_matches",
    "map_severity",
    "_coerce_dict_sequence",
    "_coerce_object_mapping",
    "_coerce_optional_str",
    "_ensure_lines",
    "_load_json_stream",
]
