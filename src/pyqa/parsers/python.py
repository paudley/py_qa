# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Parsers for Python-related tooling output."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final

from pyqa.core.severity import Severity, severity_from_code

from ..core.models import RawDiagnostic
from ..core.serialization import JsonValue, coerce_optional_int, coerce_optional_str
from ..interfaces.tools import ToolContext
from .base import (
    DiagnosticDetails,
    DiagnosticLocation,
    append_diagnostic,
    iter_dicts,
)


def _mapping_from_json(value: JsonValue | None) -> Mapping[str, JsonValue]:
    """Return ``value`` when it is a mapping, otherwise an empty mapping.

    Args:
        value: JSON value that may represent a mapping of attributes.

    Returns:
        Mapping[str, JsonValue]: Mapping extracted from *value* or an empty mapping.
    """

    return value if isinstance(value, Mapping) else {}


def _iter_mapping_sequence(value: JsonValue | None) -> tuple[Mapping[str, JsonValue], ...]:
    """Return tuple of mappings extracted from ``value`` when iterable.

    Args:
        value: JSON value that may contain a sequence of mapping entries.

    Returns:
        tuple[Mapping[str, JsonValue], ...]: Tuple containing mapping entries discovered in *value*.
    """

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(entry for entry in value if isinstance(entry, Mapping))
    return ()


def _iter_json_sequence(value: JsonValue | None) -> tuple[JsonValue, ...]:
    """Return non-string sequence items derived from ``value``.

    Args:
        value: JSON value that may contain an arbitrary sequence.

    Returns:
        tuple[JsonValue, ...]: Tuple containing entries discovered in *value*.
    """

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(value)
    return ()


def parse_ruff(payload: JsonValue, context: ToolContext) -> Sequence[RawDiagnostic]:
    """Parse Ruff JSON output into raw diagnostics.

    Args:
        payload: JSON payload returned by Ruff.
        context: Tool execution context supplied by the orchestrator.

    Returns:
        Sequence[RawDiagnostic]: Normalised diagnostics representing Ruff findings.
    """
    del context
    results: list[RawDiagnostic] = []
    if isinstance(payload, Mapping):
        source: JsonValue | None = payload.get("diagnostics")
    else:
        source = payload
    for item in iter_dicts(source):
        filename = coerce_optional_str(item.get("filename")) or coerce_optional_str(item.get("file"))
        location = _mapping_from_json(item.get("location"))
        code = coerce_optional_str(item.get("code"))
        severity = severity_from_code(code, Severity.WARNING)
        message = coerce_optional_str(item.get("message")) or ""
        diag_location = DiagnosticLocation(
            file=filename,
            line=coerce_optional_int(location.get("row")),
            column=coerce_optional_int(location.get("column")),
        )
        details = _build_python_details(
            "ruff",
            severity=severity,
            message=message,
            code=code,
        )
        append_diagnostic(results, location=diag_location, details=details)
    return results


def _normalise_pylint_code(symbol: JsonValue, item: Mapping[str, JsonValue]) -> str | None:
    """Return a Pylint diagnostic code in canonical hyphenated form.

    Args:
        symbol: Symbol value reported by Pylint for the diagnostic.
        item: Mapping describing the JSON diagnostic entry.

    Returns:
        str | None: Normalised diagnostic code or ``None`` when unavailable.
    """

    if isinstance(symbol, str) and symbol.strip():
        return symbol.strip().replace("_", "-")
    message_id = item.get("message-id")
    if isinstance(message_id, str) and message_id.strip():
        return message_id.strip()
    if message_id is not None:
        return str(message_id)
    return None


def parse_pylint(payload: JsonValue, context: ToolContext) -> Sequence[RawDiagnostic]:
    """Parse Pylint JSON output into raw diagnostics.

    Args:
        payload: JSON payload emitted by Pylint.
        context: Tool execution context supplied by the orchestrator.

    Returns:
        Sequence[RawDiagnostic]: Diagnostics prepared for downstream processing.
    """
    del context
    results: list[RawDiagnostic] = []
    for item in iter_dicts(payload):
        path = coerce_optional_str(item.get("path")) or coerce_optional_str(item.get("filename"))
        line = coerce_optional_int(item.get("line"))
        column = coerce_optional_int(item.get("column"))
        symbol = item.get("symbol")
        code = _normalise_pylint_code(symbol, item)
        message = coerce_optional_str(item.get("message")) or ""
        sev = str(item.get("type", "warning")).lower()
        severity = {
            "fatal": Severity.ERROR,
            "error": Severity.ERROR,
            "warning": Severity.WARNING,
            "convention": Severity.NOTICE,
            "refactor": Severity.NOTICE,
            "info": Severity.NOTE,
        }.get(sev, Severity.WARNING)
        diag_location = DiagnosticLocation(file=path, line=line, column=column)
        details = _build_python_details(
            "pylint",
            severity=severity,
            message=message,
            code=code,
        )
        append_diagnostic(results, location=diag_location, details=details)
    return results


def parse_pyright(payload: JsonValue, context: ToolContext) -> Sequence[RawDiagnostic]:
    """Parse Pyright JSON diagnostics.

    Args:
        payload: JSON payload emitted by Pyright.
        context: Tool execution context supplied by the orchestrator.

    Returns:
        Sequence[RawDiagnostic]: Diagnostics ready for downstream processing.
    """
    del context
    if isinstance(payload, Mapping):
        diagnostics = _iter_mapping_sequence(payload.get("generalDiagnostics"))
        if not diagnostics:
            diagnostics = _iter_mapping_sequence(payload.get("diagnostics"))
    else:
        diagnostics = tuple(iter_dicts(payload))
    results: list[RawDiagnostic] = []
    for item in diagnostics:
        path = coerce_optional_str(item.get("file")) or coerce_optional_str(item.get("path"))
        rng = _mapping_from_json(item.get("range"))
        start = _mapping_from_json(rng.get("start"))
        severity = str(item.get("severity", "warning")).lower()
        sev_enum = {
            "error": Severity.ERROR,
            "warning": Severity.WARNING,
            "information": Severity.NOTICE,
            "hint": Severity.NOTE,
        }.get(severity, Severity.WARNING)
        rule = coerce_optional_str(item.get("rule"))
        diag_location = DiagnosticLocation(
            file=path,
            line=coerce_optional_int(start.get("line")),
            column=coerce_optional_int(start.get("character")),
        )
        details = _build_python_details(
            "pyright",
            severity=sev_enum,
            message=coerce_optional_str(item.get("message")) or "",
            code=rule,
        )
        append_diagnostic(results, location=diag_location, details=details)
    return results


def _extract_mypy_function(entry: Mapping[str, JsonValue]) -> str | None:
    """Extract the function or symbol name referenced by a MyPy diagnostic.

    Args:
        entry: Mapping describing a MyPy diagnostic entry.

    Returns:
        str | None: Symbol name referenced by the diagnostic, or ``None`` if missing.
    """

    candidates = (
        entry.get("function"),
        entry.get("name"),
        entry.get("target"),
        entry.get("symbol"),
    )
    for value in candidates:
        if isinstance(value, str) and value.strip():
            return value.strip().rsplit(".", maxsplit=1)[-1]
        if value is not None:
            return str(value).rsplit(".", maxsplit=1)[-1]
    return None


def _build_python_details(
    tool: str,
    *,
    severity: Severity,
    message: str,
    code: str | None = None,
    function: str | None = None,
) -> DiagnosticDetails:
    """Return :class:`DiagnosticDetails` populated for Python tooling.

    Args:
        tool: Tool identifier associated with the diagnostic.
        severity: Enum identifying diagnostic severity.
        message: Human-readable diagnostic message.
        code: Optional diagnostic code provided by the tool.
        function: Optional function or symbol name associated with the diagnostic.

    Returns:
        DiagnosticDetails: Structured detail payload describing the diagnostic.
    """

    return DiagnosticDetails(
        severity=severity,
        message=message,
        tool=tool,
        code=code,
        function=function,
    )


def parse_mypy(payload: JsonValue, context: ToolContext) -> Sequence[RawDiagnostic]:
    """Parse MyPy JSON diagnostics.

    Args:
        payload: JSON payload produced by MyPy.
        context: Tool execution context supplied by the orchestrator.

    Returns:
        Sequence[RawDiagnostic]: Diagnostics prepared for downstream processing.
    """
    del context
    results: list[RawDiagnostic] = []
    if isinstance(payload, Mapping):
        error_entries = _iter_mapping_sequence(payload.get("errors"))
        sources = error_entries if error_entries else (payload,)
    else:
        sources = tuple(iter_dicts(payload))

    for item in sources:
        path = coerce_optional_str(item.get("path")) or coerce_optional_str(item.get("file"))
        message = coerce_optional_str(item.get("message")) or ""
        severity = str(item.get("severity", "error")).lower()
        code = coerce_optional_str(item.get("code")) or coerce_optional_str(item.get("error_code"))
        function = _extract_mypy_function(item)
        sev_enum = {
            "error": Severity.ERROR,
            "warning": Severity.WARNING,
            "note": Severity.NOTE,
        }.get(severity, Severity.WARNING)
        diag_location = DiagnosticLocation(
            file=path,
            line=coerce_optional_int(item.get("line")),
            column=coerce_optional_int(item.get("column")),
        )
        details = _build_python_details(
            "mypy",
            severity=sev_enum,
            message=message,
            code=code,
            function=function,
        )
        append_diagnostic(results, location=diag_location, details=details)
    return results


SELENE_SEVERITY_MAP: Final[dict[str, Severity]] = {
    "error": Severity.ERROR,
    "warning": Severity.WARNING,
    "note": Severity.NOTE,
    "help": Severity.NOTE,
    "info": Severity.NOTICE,
}
SELENE_DIAGNOSTIC_TYPE: Final[str] = "diagnostic"


def _iter_selene_records(payload: JsonValue) -> tuple[Mapping[str, JsonValue], ...]:
    """Return mapping entries representing Selene diagnostics.

    Args:
        payload: JSON payload produced by Selene.

    Returns:
        tuple[Mapping[str, JsonValue], ...]: Tuple of mapping entries describing Selene diagnostics.
    """

    if isinstance(payload, list):
        return tuple(item for item in payload if isinstance(item, Mapping))
    if isinstance(payload, Mapping):
        return (payload,)
    return ()


def _is_selene_diagnostic(entry: Mapping[str, JsonValue]) -> bool:
    """Return whether ``entry`` represents a diagnostic record.

    Args:
        entry: Mapping describing a potential Selene diagnostic entry.

    Returns:
        bool: ``True`` when *entry* corresponds to a diagnostic record.
    """

    entry_type = str(entry.get("type", "")).lower()
    return entry_type == SELENE_DIAGNOSTIC_TYPE


def _extract_selene_location(
    entry: Mapping[str, JsonValue],
) -> tuple[str | None, int | None, int | None]:
    """Return location metadata extracted from a Selene entry.

    Args:
        entry: Mapping describing a Selene diagnostic.

    Returns:
        tuple[str | None, int | None, int | None]: Tuple containing file, line, and column metadata.
    """

    primary = entry.get("primary_label")
    if not isinstance(primary, Mapping):
        return None, None, None
    span_value = primary.get("span")
    span_mapping = _mapping_from_json(span_value)
    line = coerce_optional_int(span_mapping.get("start_line"))
    column = coerce_optional_int(span_mapping.get("start_column"))
    if line is not None:
        line += 1
    if column is not None:
        column += 1
    return coerce_optional_str(primary.get("filename")), line, column


def _collect_selene_notes(entry: Mapping[str, JsonValue]) -> list[str]:
    """Collect supplemental notes attached to a Selene diagnostic.

    Args:
        entry: Mapping describing a Selene diagnostic entry.

    Returns:
        list[str]: List of supplemental notes associated with the diagnostic.
    """

    notes: list[str] = []
    for note in _iter_json_sequence(entry.get("notes")):
        text = coerce_optional_str(note) or ""
        if text:
            notes.append(text)
    for label in _iter_json_sequence(entry.get("secondary_labels")):
        if isinstance(label, Mapping):
            message = coerce_optional_str(label.get("message")) or ""
            if message:
                notes.append(message)
    return notes


def _build_selene_message(entry: Mapping[str, JsonValue]) -> str:
    """Construct a diagnostic message incorporating supplemental notes.

    Args:
        entry: Mapping describing a Selene diagnostic entry.

    Returns:
        str: Message string ready for inclusion in a :class:`RawDiagnostic`.
    """

    base_message = str(entry.get("message", "")).strip()
    notes = _collect_selene_notes(entry)
    if not notes:
        return base_message
    notes_content = "; ".join(notes)
    if base_message:
        return f"{base_message} ({notes_content})"
    return notes_content


def _parse_selene_entry(entry: Mapping[str, JsonValue]) -> RawDiagnostic | None:
    """Return a :class:`RawDiagnostic` constructed from ``entry`` when possible.

    Args:
        entry: Mapping describing a Selene diagnostic entry.

    Returns:
        RawDiagnostic | None: Constructed diagnostic or ``None`` when *entry* is not diagnostic.
    """

    if not _is_selene_diagnostic(entry):
        return None
    severity_label = str(entry.get("severity", "warning")).lower()
    severity = SELENE_SEVERITY_MAP.get(severity_label, Severity.WARNING)
    file_name, line, column = _extract_selene_location(entry)
    message = _build_selene_message(entry)
    return RawDiagnostic(
        file=file_name,
        line=line,
        column=column,
        severity=severity,
        message=message,
        code=coerce_optional_str(entry.get("code")),
        tool="selene",
    )


def parse_selene(payload: JsonValue, context: ToolContext) -> Sequence[RawDiagnostic]:
    """Parse Selene JSON output (display-style json2).

    Args:
        payload: JSON payload produced by Selene.
        context: Tool execution context supplied by the orchestrator.

    Returns:
        Sequence[RawDiagnostic]: Diagnostics derived from the Selene payload.
    """
    del context
    results: list[RawDiagnostic] = []
    for entry in _iter_selene_records(payload):
        diagnostic = _parse_selene_entry(entry)
        if diagnostic is None:
            continue
        results.append(diagnostic)
    return results


__all__ = [
    "parse_mypy",
    "parse_pylint",
    "parse_pyright",
    "parse_ruff",
    "parse_selene",
]
