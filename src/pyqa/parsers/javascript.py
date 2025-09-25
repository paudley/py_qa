# SPDX-License-Identifier: MIT
"""Parsers for JavaScript and TypeScript tooling."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from ..models import RawDiagnostic
from ..severity import Severity
from ..tools.base import ToolContext

_TSC_PATTERN = re.compile(
    r"^(?P<file>[^:(\n]+)\((?P<line>\d+),(?P<col>\d+)\):\s*"
    r"(?P<severity>error|warning)\s*(?P<code>[A-Z]+\d+)?\s*:?\s*(?P<message>.+)$",
)


def parse_eslint(payload: Any, _context: ToolContext) -> Sequence[RawDiagnostic]:
    """Parse ESLint JSON output."""
    items = payload if isinstance(payload, list) else []
    results: list[RawDiagnostic] = []
    for entry in items:
        if not isinstance(entry, dict):
            continue
        path = entry.get("filePath") or entry.get("filename")
        for message in entry.get("messages", []) or []:
            if not isinstance(message, dict):
                continue
            severity = message.get("severity", 1)
            if severity == 2:
                sev_enum = Severity.ERROR
            elif severity == 1:
                sev_enum = Severity.WARNING
            else:
                sev_enum = Severity.NOTICE
            code = message.get("ruleId")
            results.append(
                RawDiagnostic(
                    file=path,
                    line=message.get("line"),
                    column=message.get("column"),
                    severity=sev_enum,
                    message=str(message.get("message", "")).strip(),
                    code=code,
                    tool="eslint",
                ),
            )
    return results


def parse_stylelint(payload: Any, _context: ToolContext) -> Sequence[RawDiagnostic]:
    """Parse stylelint JSON output."""
    items = payload if isinstance(payload, list) else []
    results: list[RawDiagnostic] = []
    for entry in items:
        if not isinstance(entry, dict):
            continue
        source = entry.get("source") or entry.get("file")
        warnings = entry.get("warnings")
        if not isinstance(warnings, list):
            continue
        for warning in warnings:
            if not isinstance(warning, dict):
                continue
            message = str(warning.get("text", "")).strip()
            if not message:
                continue
            severity_label = str(warning.get("severity", "warning")).lower()
            severity = {
                "error": Severity.ERROR,
                "warning": Severity.WARNING,
            }.get(severity_label, Severity.WARNING)
            rule = warning.get("rule")
            results.append(
                RawDiagnostic(
                    file=source,
                    line=warning.get("line"),
                    column=warning.get("column"),
                    severity=severity,
                    message=message,
                    code=str(rule) if rule else None,
                    tool="stylelint",
                ),
            )
    return results


def parse_tsc(stdout: str, _context: ToolContext) -> Sequence[RawDiagnostic]:
    """Parse TypeScript compiler text diagnostics."""
    results: list[RawDiagnostic] = []
    for line in stdout.splitlines():
        match = _TSC_PATTERN.match(line.strip())
        if not match:
            continue
        severity = Severity.ERROR if match.group("severity") == "error" else Severity.WARNING
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
