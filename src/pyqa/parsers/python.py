# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Parsers for Python-related tooling output."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any, Final

from ..models import RawDiagnostic
from ..severity import Severity, severity_from_code
from ..tools.base import ToolContext


def parse_ruff(payload: Any, _context: ToolContext) -> Sequence[RawDiagnostic]:
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
        filename = item.get("filename") or item.get("file")
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


def parse_pylint(payload: Any, _context: ToolContext) -> Sequence[RawDiagnostic]:
    """Parse Pylint JSON output into raw diagnostics."""
    items = payload if isinstance(payload, list) else []
    results: list[RawDiagnostic] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        path = item.get("path") or item.get("filename")
        line = item.get("line")
        column = item.get("column")
        symbol = item.get("symbol")
        if isinstance(symbol, str) and symbol:
            code = symbol.strip().replace("_", "-")
        else:
            code = item.get("message-id")
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


def parse_pyright(payload: Any, _context: ToolContext) -> Sequence[RawDiagnostic]:
    """Parse Pyright JSON diagnostics."""
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


def parse_mypy(payload: Any, _context: ToolContext) -> Sequence[RawDiagnostic]:
    """Parse MyPy JSON diagnostics."""
    items = payload if isinstance(payload, list) else []
    results: list[RawDiagnostic] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        path = item.get("path") or item.get("file")
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


def parse_selene(payload: Any, _context: ToolContext) -> Sequence[RawDiagnostic]:
    """Parse selene JSON output (display-style json2)."""
    records: Iterable[dict[str, Any]]
    if isinstance(payload, list):
        records = [item for item in payload if isinstance(item, dict)]
    elif isinstance(payload, dict):
        records = [payload]
    else:
        records = []

    results: list[RawDiagnostic] = []
    for entry in records:
        entry_type = str(entry.get("type", "")).lower()
        if entry_type == "summary":
            continue
        if entry_type != "diagnostic":
            continue

        severity_label = str(entry.get("severity", "warning")).lower()
        severity = SELENE_SEVERITY_MAP.get(severity_label, Severity.WARNING)
        primary = entry.get("primary_label") or {}
        if not isinstance(primary, dict):
            primary = {}
        span = primary.get("span") or {}
        if not isinstance(span, dict):
            span = {}
        line = span.get("start_line")
        column = span.get("start_column")
        if isinstance(line, int):
            line += 1
        if isinstance(column, int):
            column += 1

        notes: list[str] = []
        for note in entry.get("notes", []) or []:
            text = str(note).strip()
            if text:
                notes.append(text)
        for label in entry.get("secondary_labels", []) or []:
            if isinstance(label, dict):
                message = str(label.get("message", "")).strip()
                if message:
                    notes.append(message)

        message = str(entry.get("message", "")).strip()
        if notes:
            message = f"{message} ({'; '.join(notes)})" if message else "; ".join(notes)

        results.append(
            RawDiagnostic(
                file=primary.get("filename"),
                line=line,
                column=column,
                severity=severity,
                message=message,
                code=entry.get("code"),
                tool="selene",
            ),
        )

    return results


__all__ = [
    "parse_mypy",
    "parse_pylint",
    "parse_pyright",
    "parse_ruff",
    "parse_selene",
]
