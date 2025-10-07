# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Parsers for Python-related tooling output."""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from typing import Any, Final

from pyqa.core.severity import Severity, severity_from_code

from ..core.models import RawDiagnostic
from ..tools.base import ToolContext
from .base import (
    DiagnosticDetails,
    DiagnosticLocation,
    append_diagnostic,
    iter_dicts,
)


def parse_ruff(payload: Any, context: ToolContext) -> Sequence[RawDiagnostic]:
    """Parse Ruff JSON output into raw diagnostics.

    Args:
        payload: JSON payload returned by Ruff.
        context: Tool execution context supplied by the orchestrator.

    Returns:
        Sequence[RawDiagnostic]: Normalised diagnostics representing Ruff findings.
    """
    del context
    results: list[RawDiagnostic] = []
    source = payload.get("diagnostics") if isinstance(payload, Mapping) else payload
    for item in iter_dicts(source):
        filename = item.get("filename") or item.get("file")
        location = item.get("location") or {}
        code = item.get("code")
        severity = severity_from_code(code or "", Severity.WARNING)
        message = str(item.get("message", "")).strip()
        diag_location = DiagnosticLocation(
            file=filename,
            line=location.get("row"),
            column=location.get("column"),
        )
        details = _build_python_details(
            "ruff",
            severity=severity,
            message=message,
            code=code,
        )
        append_diagnostic(results, location=diag_location, details=details)
    return results


def _normalise_pylint_code(symbol: object, item: Mapping[str, Any]) -> str | None:
    """Return a Pylint diagnostic code in canonical hyphenated form."""

    if isinstance(symbol, str) and symbol.strip():
        return symbol.strip().replace("_", "-")
    message_id = item.get("message-id")
    if isinstance(message_id, str) and message_id.strip():
        return message_id.strip()
    if message_id is not None:
        return str(message_id)
    return None


def parse_pylint(payload: Any, context: ToolContext) -> Sequence[RawDiagnostic]:
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
        path = item.get("path") or item.get("filename")
        line = item.get("line")
        column = item.get("column")
        symbol = item.get("symbol")
        code = _normalise_pylint_code(symbol, item)
        message = str(item.get("message", "")).strip()
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


def parse_pyright(payload: Any, context: ToolContext) -> Sequence[RawDiagnostic]:
    """Parse Pyright JSON diagnostics.

    Args:
        payload: JSON payload emitted by Pyright.
        context: Tool execution context supplied by the orchestrator.

    Returns:
        Sequence[RawDiagnostic]: Diagnostics ready for downstream processing.
    """
    del context
    diagnostics = []
    if isinstance(payload, dict):
        diagnostics = payload.get("generalDiagnostics", []) or payload.get("diagnostics", [])
    results: list[RawDiagnostic] = []
    for item in diagnostics:
        if not isinstance(item, dict):
            continue
        path = item.get("file") or item.get("path")
        rng = item.get("range") or {}
        start = rng.get("start") or {}
        severity = str(item.get("severity", "warning")).lower()
        sev_enum = {
            "error": Severity.ERROR,
            "warning": Severity.WARNING,
            "information": Severity.NOTICE,
            "hint": Severity.NOTE,
        }.get(severity, Severity.WARNING)
        rule = item.get("rule")
        diag_location = DiagnosticLocation(
            file=path,
            line=start.get("line"),
            column=start.get("character"),
        )
        details = _build_python_details(
            "pyright",
            severity=sev_enum,
            message=str(item.get("message", "")).strip(),
            code=rule,
        )
        append_diagnostic(results, location=diag_location, details=details)
    return results


def _extract_mypy_function(entry: Mapping[str, Any]) -> str | None:
    """Extract the function or symbol name referenced by a MyPy diagnostic."""

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
    """Construct :class:`DiagnosticDetails` for Python tooling."""

    return DiagnosticDetails(
        severity=severity,
        message=message,
        tool=tool,
        code=code,
        function=function,
    )


def parse_mypy(payload: Any, context: ToolContext) -> Sequence[RawDiagnostic]:
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
        error_entries = payload.get("errors")
        if isinstance(error_entries, Sequence):
            sources = [entry for entry in error_entries if isinstance(entry, Mapping)]
        else:
            sources = [payload]
    else:
        sources = list(iter_dicts(payload))

    for item in sources:
        path = item.get("path") or item.get("file")
        message = str(item.get("message", "")).strip()
        severity = str(item.get("severity", "error")).lower()
        code = item.get("code") or item.get("error_code")
        function = _extract_mypy_function(item)
        sev_enum = {
            "error": Severity.ERROR,
            "warning": Severity.WARNING,
            "note": Severity.NOTE,
        }.get(severity, Severity.WARNING)
        diag_location = DiagnosticLocation(
            file=path,
            line=item.get("line"),
            column=item.get("column"),
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


def _iter_selene_records(payload: Any) -> Iterator[dict[str, Any]]:
    if isinstance(payload, list):
        yield from (item for item in payload if isinstance(item, dict))
    elif isinstance(payload, dict):
        yield payload


def _is_selene_diagnostic(entry: Mapping[str, Any]) -> bool:
    entry_type = str(entry.get("type", "")).lower()
    return entry_type == SELENE_DIAGNOSTIC_TYPE


def _extract_selene_location(entry: Mapping[str, Any]) -> tuple[str | None, int | None, int | None]:
    primary = entry.get("primary_label")
    if not isinstance(primary, Mapping):
        return None, None, None
    span = primary.get("span")
    span_mapping = span if isinstance(span, Mapping) else {}
    line = span_mapping.get("start_line")
    column = span_mapping.get("start_column")
    if isinstance(line, int):
        line += 1
    else:
        line = None
    if isinstance(column, int):
        column += 1
    else:
        column = None
    return primary.get("filename"), line, column


def _collect_selene_notes(entry: Mapping[str, Any]) -> list[str]:
    notes: list[str] = []
    for note in entry.get("notes", []) or []:
        text = str(note).strip()
        if text:
            notes.append(text)
    for label in entry.get("secondary_labels", []) or []:
        if isinstance(label, Mapping):
            message = str(label.get("message", "")).strip()
            if message:
                notes.append(message)
    return notes


def _build_selene_message(entry: Mapping[str, Any]) -> str:
    base_message = str(entry.get("message", "")).strip()
    notes = _collect_selene_notes(entry)
    if not notes:
        return base_message
    notes_content = "; ".join(notes)
    if base_message:
        return f"{base_message} ({notes_content})"
    return notes_content


def _parse_selene_entry(entry: Mapping[str, Any]) -> RawDiagnostic | None:
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
        code=entry.get("code"),
        tool="selene",
    )


def parse_selene(payload: Any, _context: ToolContext) -> Sequence[RawDiagnostic]:
    """Parse selene JSON output (display-style json2)."""
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
