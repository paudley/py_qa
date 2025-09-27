# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Parsers for Python-related tooling output."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from ..models import RawDiagnostic
from ..path_utils import normalize_reported_path
from ..severity import Severity, severity_from_code
from ..tools.base import ToolContext


def parse_ruff(payload: Any, context: ToolContext) -> Sequence[RawDiagnostic]:
    """Parse Ruff JSON output into raw diagnostics."""
    items: Iterable[dict[str, Any]]
    if isinstance(payload, dict):
        items = payload.get("diagnostics", [])  # for future compatibility
    elif isinstance(payload, list):
        items = [item for item in payload if isinstance(item, dict)]
    else:
        items = []

    results: list[RawDiagnostic] = []
    for item in items:
        filename = normalize_reported_path(
            item.get("filename") or item.get("file"),
            root=context.root,
        )
        location = item.get("location") or {}
        code = item.get("code")
        severity = severity_from_code(code or "", Severity.WARNING)
        message = str(item.get("message", "")).strip()
        results.append(
            RawDiagnostic(
                file=filename,
                line=location.get("row"),
                column=location.get("column"),
                severity=severity,
                message=message,
                code=code,
                tool="ruff",
            ),
        )
    return results


def parse_pylint(payload: Any, context: ToolContext) -> Sequence[RawDiagnostic]:
    """Parse Pylint JSON output into raw diagnostics."""
    items = payload if isinstance(payload, list) else []
    results: list[RawDiagnostic] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        path = normalize_reported_path(
            item.get("path") or item.get("filename"),
            root=context.root,
        )
        line = item.get("line")
        column = item.get("column")
        symbol = item.get("symbol")
        if isinstance(symbol, str) and symbol:
            code = symbol.strip().replace("_", "-")
        else:
            code = item.get("message-id")
        message = _format_pylint_message(
            str(item.get("message", "")).strip(),
            code,
        )
        sev = str(item.get("type", "warning")).lower()
        severity = {
            "fatal": Severity.ERROR,
            "error": Severity.ERROR,
            "warning": Severity.WARNING,
            "convention": Severity.NOTICE,
            "refactor": Severity.NOTICE,
            "info": Severity.NOTE,
        }.get(sev, Severity.WARNING)
        results.append(
            RawDiagnostic(
                file=path,
                line=line,
                column=column,
                severity=severity,
                message=message,
                code=code,
                tool="pylint",
            ),
        )
    return results


def parse_pyright(payload: Any, context: ToolContext) -> Sequence[RawDiagnostic]:
    """Parse Pyright JSON diagnostics."""
    diagnostics = []
    if isinstance(payload, dict):
        diagnostics = payload.get("generalDiagnostics", []) or payload.get("diagnostics", [])
    results: list[RawDiagnostic] = []
    for item in diagnostics:
        if not isinstance(item, dict):
            continue
        path = normalize_reported_path(
            item.get("file") or item.get("path"),
            root=context.root,
        )
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
        results.append(
            RawDiagnostic(
                file=path,
                line=start.get("line"),
                column=start.get("character"),
                severity=sev_enum,
                message=str(item.get("message", "")).strip(),
                code=rule,
                tool="pyright",
            ),
        )
    return results


def parse_mypy(payload: Any, context: ToolContext) -> Sequence[RawDiagnostic]:
    """Parse MyPy JSON diagnostics."""
    items = payload if isinstance(payload, list) else []
    results: list[RawDiagnostic] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        path = normalize_reported_path(
            item.get("path") or item.get("file"),
            root=context.root,
        )
        message = str(item.get("message", "")).strip()
        severity = str(item.get("severity", "error")).lower()
        code = item.get("code") or item.get("error_code")
        function = (
            item.get("function") or item.get("name") or item.get("target") or item.get("symbol")
        )
        if isinstance(function, str) and function:
            function = function.split(".")[-1]
        else:
            function = None
        sev_enum = {
            "error": Severity.ERROR,
            "warning": Severity.WARNING,
            "note": Severity.NOTE,
        }.get(severity, Severity.WARNING)
        results.append(
            RawDiagnostic(
                file=path,
                line=item.get("line"),
                column=item.get("column"),
                severity=sev_enum,
                message=message,
                code=code,
                tool="mypy",
                function=function,
            ),
        )
    return results


SELENE_SEVERITY_MAP: Final[dict[str, Severity]] = {
    "error": Severity.ERROR,
    "warning": Severity.WARNING,
    "note": Severity.NOTE,
    "help": Severity.NOTE,
    "info": Severity.NOTICE,
}


def parse_selene(payload: Any, context: ToolContext) -> Sequence[RawDiagnostic]:
    """Parse selene JSON output (display-style json2)."""
    records = _selene_records(payload)
    results: list[RawDiagnostic] = []
    for entry in records:
        diagnostic = _parse_selene_record(entry, context.root)
        if diagnostic is not None:
            results.append(diagnostic)
    return results


def _format_pylint_message(message: str, code: str | None) -> str:
    if code != "duplicate-code":
        return message
    lines = [line.strip() for line in message.splitlines() if line.strip()]
    if not lines:
        return message
    header = lines[0]
    clones: list[str] = []
    for line in lines[1:]:
        if not line.startswith("=="):
            break
        clones.append(line[2:])
    if not clones:
        return header
    return f"{header} ({'; '.join(clones)})"


def _selene_records(payload: Any) -> Iterable[Mapping[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, Mapping)]
    if isinstance(payload, Mapping):
        return [payload]
    return []


def _parse_selene_record(entry: Mapping[str, Any], root: Path) -> RawDiagnostic | None:
    entry_type = str(entry.get("type", "")).lower()
    if entry_type != "diagnostic":
        return None

    severity_label = str(entry.get("severity", "warning")).lower()
    severity = SELENE_SEVERITY_MAP.get(severity_label, Severity.WARNING)

    primary = entry.get("primary_label")
    primary_map = primary if isinstance(primary, Mapping) else {}
    file_path, line, column = _selene_primary_span(primary_map)
    file_path = normalize_reported_path(file_path, root=root)

    message = _selene_message(entry, primary_map)

    return RawDiagnostic(
        file=file_path,
        line=line,
        column=column,
        severity=severity,
        message=message,
        code=entry.get("code"),
        tool="selene",
    )


def _selene_primary_span(primary: Mapping[str, Any]) -> tuple[str | None, int | None, int | None]:
    span = primary.get("span")
    span_map = span if isinstance(span, Mapping) else {}

    line = span_map.get("start_line")
    column = span_map.get("start_column")
    if isinstance(line, int):
        line += 1
    else:
        line = None
    if isinstance(column, int):
        column += 1
    else:
        column = None

    filename = primary.get("filename")
    if not isinstance(filename, str):
        filename = None

    return filename, line, column


def _selene_message(
    entry: Mapping[str, Any],
    primary: Mapping[str, Any],
) -> str:
    base_message = str(entry.get("message", "")).strip()
    fragments: list[str] = []
    for note in entry.get("notes", []) or []:
        text = str(note).strip()
        if text:
            fragments.append(text)
    for label in entry.get("secondary_labels", []) or []:
        if not isinstance(label, Mapping):
            continue
        message = str(label.get("message", "")).strip()
        if message:
            fragments.append(message)

    if not fragments:
        return base_message
    joined = "; ".join(fragments)
    if not base_message:
        return joined
    return f"{base_message} ({joined})"


__all__ = [
    "parse_mypy",
    "parse_pylint",
    "parse_pyright",
    "parse_ruff",
    "parse_selene",
]
