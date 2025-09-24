# SPDX-License-Identifier: MIT
"""Parsers for assorted tooling across ecosystems."""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from typing import Any, Final

from ..models import RawDiagnostic
from ..serialization import coerce_optional_int
from ..severity import Severity
from ..tools.base import ToolContext


def parse_shfmt(stdout: str, _context: ToolContext) -> Sequence[RawDiagnostic]:
    """Parse shfmt diff output."""

    results: list[RawDiagnostic] = []
    current_file: str | None = None
    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if line.startswith("diff -u"):
            parts = line.split()
            if len(parts) >= 4:
                current_file = parts[-1]
            continue
        if line.startswith("--- "):
            current_file = line[4:].strip()
            if current_file.startswith("a/"):
                current_file = current_file[2:]
            continue
        if line.startswith("+++"):
            current_file = line[4:].strip()
            if current_file.startswith("b/"):
                current_file = current_file[2:]
            results.append(
                RawDiagnostic(
                    file=current_file,
                    line=None,
                    column=None,
                    severity=Severity.WARNING,
                    message="File is not formatted according to shfmt",
                    code="format",
                    tool="shfmt",
                )
            )
            continue
    return results


PHPLINT_PATTERN = re.compile(
    r"^Parse error: (?P<message>.+?) in (?P<file>.+) on line (?P<line>\d+)"
)


def parse_phplint(stdout: str, _context: ToolContext) -> Sequence[RawDiagnostic]:
    """Parse phplint textual output."""

    results: list[RawDiagnostic] = []
    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = PHPLINT_PATTERN.match(line)
        if not match:
            continue
        try:
            line_no = int(match.group("line"))
        except ValueError:
            line_no = None
        results.append(
            RawDiagnostic(
                file=match.group("file"),
                line=line_no,
                column=None,
                severity=Severity.ERROR,
                message=match.group("message").strip(),
                code="parse-error",
                tool="phplint",
            )
        )
    return results


PERLCRITIC_PATTERN = re.compile(
    r"^(?P<file>[^:]+):(?P<line>\d+):(?P<column>\d+):\s*(?P<message>.+?)\s*\((?P<rule>[^)]+)\)$"
)


def parse_perlcritic(stdout: str, _context: ToolContext) -> Sequence[RawDiagnostic]:
    """Parse perlcritic textual output using custom verbose template."""

    results: list[RawDiagnostic] = []
    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = PERLCRITIC_PATTERN.match(line)
        if not match:
            continue
        message = match.group("message").strip()
        results.append(
            RawDiagnostic(
                file=match.group("file"),
                line=int(match.group("line")),
                column=int(match.group("column")),
                severity=Severity.WARNING,
                message=message,
                code=match.group("rule"),
                tool="perlcritic",
            )
        )
    return results


def parse_checkmake(payload: Any, _context: ToolContext) -> Sequence[RawDiagnostic]:
    """Parse checkmake JSON output."""

    files: list[dict[str, Any]]
    if isinstance(payload, dict):
        files = payload.get("files") or payload.get("results") or []
    elif isinstance(payload, list):
        files = [entry for entry in payload if isinstance(entry, dict)]
    else:
        files = []

    results: list[RawDiagnostic] = []
    for entry in files:
        file_path = entry.get("file") or entry.get("filename") or entry.get("name")
        issues = entry.get("errors") or entry.get("warnings") or entry.get("issues")
        if not isinstance(issues, list):
            continue
        for issue in issues:
            if not isinstance(issue, dict):
                continue
            message = issue.get("message") or issue.get("description")
            if not message:
                continue
            rule = issue.get("rule") or issue.get("code")
            severity_label = issue.get("severity") or issue.get("level") or "warning"
            severity = {
                "error": Severity.ERROR,
                "warning": Severity.WARNING,
                "info": Severity.NOTICE,
            }.get(str(severity_label).lower(), Severity.WARNING)
            line = issue.get("line")
            column = issue.get("column") or issue.get("col")
            results.append(
                RawDiagnostic(
                    file=file_path,
                    line=line,
                    column=column,
                    severity=severity,
                    message=str(message).strip(),
                    code=str(rule) if rule else None,
                    tool="checkmake",
                )
            )
    return results


_CPPLINT_PATTERN = re.compile(
    r"^(?P<file>[^:]+):(?P<line>\d+):\s+(?P<message>.+?)\s+\[(?P<category>[^\]]+)\]\s+\[(?P<confidence>\d+)\]$"
)


def parse_cpplint(stdout: str, _context: ToolContext) -> Sequence[RawDiagnostic]:
    """Parse cpplint text diagnostics."""

    results: list[RawDiagnostic] = []
    for line in stdout.splitlines():
        stripped = line.strip()
        if (
            not stripped
            or stripped.startswith("Done processing")
            or stripped.startswith("Total errors")
        ):
            continue
        match = _CPPLINT_PATTERN.match(stripped)
        if not match:
            continue
        message = match.group("message").strip()
        category = match.group("category").strip()
        results.append(
            RawDiagnostic(
                file=match.group("file"),
                line=int(match.group("line")),
                column=None,
                severity=Severity.WARNING,
                message=message,
                code=category,
                tool="cpplint",
            )
        )
    return results


_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*m")
_TOMBI_HEADER_RE = re.compile(
    r"^(?P<level>Error|Warning|Info|Hint|Note):\s*(?P<message>.+)$", re.IGNORECASE
)
_TOMBI_LOCATION_RE = re.compile(
    r"^at\s+(?P<file>.+?)(?::(?P<line>\d+))?(?::(?P<column>\d+))?$",
    re.IGNORECASE,
)
TOMBI_SEVERITY_MAP: Final[dict[str, Severity]] = {
    "error": Severity.ERROR,
    "warning": Severity.WARNING,
    "warn": Severity.WARNING,
    "info": Severity.NOTICE,
    "hint": Severity.NOTE,
    "note": Severity.NOTE,
}


def parse_tombi(stdout: str, _context: ToolContext) -> Sequence[RawDiagnostic]:
    """Parse tombi lint textual diagnostics."""

    cleaned = _ANSI_ESCAPE_RE.sub("", stdout)
    results: list[RawDiagnostic] = []
    for header, body in _split_tombi_blocks(cleaned.splitlines()):
        diagnostic = _build_tombi_diagnostic(header, body)
        if diagnostic is not None:
            results.append(diagnostic)
    return results


def _split_tombi_blocks(lines: Sequence[str]) -> Iterable[tuple[str, list[str]]]:
    current_header: str | None = None
    current_body: list[str] = []
    for raw_line in lines:
        line = raw_line.strip()
        header = _TOMBI_HEADER_RE.match(line)
        if header:
            if current_header is not None:
                yield current_header, current_body
            current_header = line
            current_body = []
            continue
        if current_header is not None and line:
            current_body.append(line)
    if current_header is not None:
        yield current_header, current_body


def _build_tombi_diagnostic(
    header_line: str, body: Sequence[str]
) -> RawDiagnostic | None:
    header = _TOMBI_HEADER_RE.match(header_line)
    if not header:
        return None
    severity = TOMBI_SEVERITY_MAP.get(header.group("level").lower(), Severity.WARNING)
    message = header.group("message").strip()
    file_path: str | None = None
    line_no: int | None = None
    column_no: int | None = None

    for entry in body:
        location = _TOMBI_LOCATION_RE.match(entry)
        if location:
            file_path = location.group("file")
            line_no = coerce_optional_int(location.group("line"))
            column_no = coerce_optional_int(location.group("column"))
            continue
        message = f"{message} ({entry})" if message else entry

    return RawDiagnostic(
        file=file_path,
        line=line_no,
        column=column_no,
        severity=severity,
        message=message,
        code=None,
        tool="tombi",
    )


def parse_golangci_lint(payload: Any, _context: ToolContext) -> Sequence[RawDiagnostic]:
    """Parse golangci-lint JSON output."""
    issues: Iterable[dict[str, Any]]
    if isinstance(payload, dict):
        issues = payload.get("Issues") or payload.get("issues") or []
    elif isinstance(payload, list):
        issues = payload
    else:
        issues = []

    results: list[RawDiagnostic] = []
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        pos = issue.get("Pos") or issue.get("position") or {}
        path = pos.get("Filename") or pos.get("filename") or issue.get("file")
        line = pos.get("Line") or pos.get("line")
        column = pos.get("Column") or pos.get("column")
        severity = str(issue.get("Severity", "warning")).lower()
        sev_enum = {
            "error": Severity.ERROR,
            "warning": Severity.WARNING,
            "info": Severity.NOTICE,
        }.get(severity, Severity.WARNING)
        sub_linter = issue.get("FromLinter") or issue.get("source") or "golangci-lint"
        message = str(issue.get("Text", "") or issue.get("text", "")).strip()
        code = issue.get("Code") or issue.get("code")
        results.append(
            RawDiagnostic(
                file=path,
                line=line,
                column=column,
                severity=sev_enum,
                message=message,
                code=code,
                tool=str(sub_linter),
            )
        )
    return results


def parse_cargo_clippy(payload: Any, _context: ToolContext) -> Sequence[RawDiagnostic]:
    """Parse Cargo clippy JSON payloads."""
    records = (
        payload
        if isinstance(payload, list)
        else [payload] if isinstance(payload, dict) else []
    )
    results: list[RawDiagnostic] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        if record.get("reason") != "compiler-message":
            continue
        message = record.get("message", {})
        if not isinstance(message, dict):
            continue
        level = message.get("level", "warning")
        spans = message.get("spans") or []
        primary = next(
            (span for span in spans if span.get("is_primary")),
            spans[0] if spans else None,
        )
        file_name = primary.get("file_name") if isinstance(primary, dict) else None
        line = primary.get("line_start") if isinstance(primary, dict) else None
        column = primary.get("column_start") if isinstance(primary, dict) else None
        code_obj = message.get("code") or {}
        code = code_obj.get("code") if isinstance(code_obj, dict) else None
        sev_enum = {
            "error": Severity.ERROR,
            "warning": Severity.WARNING,
            "note": Severity.NOTE,
            "help": Severity.NOTE,
        }.get(str(level).lower(), Severity.WARNING)
        results.append(
            RawDiagnostic(
                file=file_name,
                line=line,
                column=column,
                severity=sev_enum,
                message=str(message.get("message", "")).strip(),
                code=code,
                tool="cargo-clippy",
            )
        )
    return results


__all__ = [
    "parse_shfmt",
    "parse_phplint",
    "parse_perlcritic",
    "parse_checkmake",
    "parse_cpplint",
    "parse_tombi",
    "parse_golangci_lint",
    "parse_cargo_clippy",
]
