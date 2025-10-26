# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Parsers for JavaScript and TypeScript tooling."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Final

from pyqa.core.serialization import JsonValue, coerce_optional_int, coerce_optional_str
from pyqa.core.severity import Severity

from ..core.models import RawDiagnostic
from ..tools.base import ToolContext

_TSC_PATTERN = re.compile(
    r"^(?P<file>[^:(\n]+)\((?P<line>\d+),(?P<col>\d+)\):\s*"
    r"(?P<severity>error|warning)\s*(?P<code>[A-Z]+\d+)?\s*:?\s*(?P<message>.+)$",
)
_ESLINT_ERROR_LEVEL: Final[int] = 2
_ESLINT_WARNING_LEVEL: Final[int] = 1
_TSC_ERROR_LABEL: Final[str] = "error"


def parse_eslint(payload: JsonValue, _context: ToolContext) -> Sequence[RawDiagnostic]:
    """Parse ESLint JSON diagnostics into raw diagnostic objects.

    Args:
        payload: JSON payload produced by ESLint when invoked with ``--format json``.
        _context: Tool execution context supplied by the orchestrator (unused).

    Returns:
        Sequence[RawDiagnostic]: Diagnostics derived from the ESLint result set.
    """
    items = payload if isinstance(payload, Sequence) and not isinstance(payload, (str, bytes, bytearray)) else []
    results: list[RawDiagnostic] = []
    for entry in items:
        if not isinstance(entry, dict):
            continue
        path = coerce_optional_str(entry.get("filePath")) or coerce_optional_str(entry.get("filename"))
        messages = entry.get("messages")
        if not isinstance(messages, Sequence):
            continue
        for message in messages:
            if not isinstance(message, dict):
                continue
            severity_level = coerce_optional_int(message.get("severity"))
            if severity_level is None:
                severity_level = _ESLINT_WARNING_LEVEL
            if severity_level == _ESLINT_ERROR_LEVEL:
                sev_enum = Severity.ERROR
            elif severity_level == _ESLINT_WARNING_LEVEL:
                sev_enum = Severity.WARNING
            else:
                sev_enum = Severity.NOTICE
            code = coerce_optional_str(message.get("ruleId"))
            line = coerce_optional_int(message.get("line"))
            column = coerce_optional_int(message.get("column"))
            text = coerce_optional_str(message.get("message")) or ""
            results.append(
                RawDiagnostic(
                    file=path,
                    line=line,
                    column=column,
                    severity=sev_enum,
                    message=text.strip(),
                    code=code,
                    tool="eslint",
                ),
            )
    return results


def parse_stylelint(payload: JsonValue, _context: ToolContext) -> Sequence[RawDiagnostic]:
    """Parse stylelint JSON diagnostics into raw diagnostic objects.

    Args:
        payload: JSON payload produced by stylelint.
        _context: Tool execution context supplied by the orchestrator (unused).

    Returns:
        Sequence[RawDiagnostic]: Diagnostics describing stylelint findings.
    """
    items = payload if isinstance(payload, Sequence) and not isinstance(payload, (str, bytes, bytearray)) else []
    results: list[RawDiagnostic] = []
    for entry in items:
        if not isinstance(entry, dict):
            continue
        source = coerce_optional_str(entry.get("source")) or coerce_optional_str(entry.get("file"))
        warnings = entry.get("warnings")
        if not isinstance(warnings, Sequence):
            continue
        for warning in warnings:
            if not isinstance(warning, dict):
                continue
            message = coerce_optional_str(warning.get("text")) or ""
            if not message:
                continue
            severity_label = str(warning.get("severity", "warning")).lower()
            severity = {
                "error": Severity.ERROR,
                "warning": Severity.WARNING,
            }.get(severity_label, Severity.WARNING)
            rule = coerce_optional_str(warning.get("rule"))
            results.append(
                RawDiagnostic(
                    file=source,
                    line=coerce_optional_int(warning.get("line")),
                    column=coerce_optional_int(warning.get("column")),
                    severity=severity,
                    message=message,
                    code=rule,
                    tool="stylelint",
                ),
            )
    return results


def parse_tsc(stdout: Sequence[str], _context: ToolContext) -> Sequence[RawDiagnostic]:
    """Parse TypeScript compiler textual diagnostics.

    Args:
        stdout: Sequence of textual TypeScript compiler diagnostics.
        _context: Tool execution context supplied by the orchestrator (unused).

    Returns:
        Sequence[RawDiagnostic]: Diagnostics surfaced by ``tsc`` execution.
    """
    results: list[RawDiagnostic] = []
    for line in stdout:
        match = _TSC_PATTERN.match(line.strip())
        if not match:
            continue
        severity = Severity.ERROR if match.group("severity") == _TSC_ERROR_LABEL else Severity.WARNING
        code = match.group("code")
        results.append(
            RawDiagnostic(
                file=match.group("file"),
                line=int(match.group("line")),
                column=int(match.group("col")),
                severity=severity,
                message=match.group("message").strip(),
                code=code,
                tool="tsc",
            ),
        )
    return results


__all__ = [
    "parse_eslint",
    "parse_stylelint",
    "parse_tsc",
]
