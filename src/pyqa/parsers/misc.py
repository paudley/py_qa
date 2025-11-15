# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Parsers for assorted tooling across ecosystems."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Final

from pyqa.core.severity import Severity

from ..core.models import RawDiagnostic
from ..core.serialization import JsonValue, coerce_optional_int, coerce_optional_str
from ..interfaces.tools import ToolContext
from .base import (
    DiagnosticDetails,
    DiagnosticLocation,
    append_diagnostic,
    create_spec,
    first_mapping,
    iter_dicts,
    map_severity,
    mapping_sequence,
)

SHFMT_DIFF_PREFIX_LENGTH: Final[int] = 4
SHFMT_MIN_HEADER_PARTS: Final[int] = 4
CARGO_CLIPPY_DIAGNOSTIC_REASON: Final[str] = "compiler-message"
GOLANGCI_SEVERITY_MAP: Final[dict[str, Severity]] = {
    "error": Severity.ERROR,
    "warning": Severity.WARNING,
    "info": Severity.NOTICE,
}
CHECKMAKE_SEVERITY_MAP: Final[dict[str, Severity]] = {
    "error": Severity.ERROR,
    "warning": Severity.WARNING,
    "info": Severity.NOTICE,
}
SHELLCHECK_SEVERITY_MAP: Final[dict[str, Severity]] = {
    "error": Severity.ERROR,
    "warning": Severity.WARNING,
    "info": Severity.NOTICE,
    "style": Severity.NOTE,
}


def parse_shfmt(stdout: Sequence[str], context: ToolContext) -> Sequence[RawDiagnostic]:
    """Parse shfmt unified diff output lines into diagnostics.

    Args:
        stdout: Sequence of shfmt output lines.
        context: Tool execution context supplied by the orchestrator.

    Returns:
        Sequence[RawDiagnostic]: Diagnostics indicating files requiring reformatting.
    """

    del context
    results: list[RawDiagnostic] = []
    current_file: str | None = None
    for raw_line in stdout:
        line = raw_line.strip()
        if line.startswith("diff -u"):
            parts = line.split()
            if len(parts) >= SHFMT_MIN_HEADER_PARTS:
                current_file = parts[-1]
            continue
        if line.startswith("--- "):
            current_file = line[SHFMT_DIFF_PREFIX_LENGTH:].strip().removeprefix("a/")
            continue
        if line.startswith("+++"):
            current_file = line[SHFMT_DIFF_PREFIX_LENGTH:].strip().removeprefix("b/")
            location = DiagnosticLocation(file=current_file, line=None, column=None)
            details = DiagnosticDetails(
                severity=Severity.WARNING,
                message="File is not formatted according to shfmt",
                tool="shfmt",
                code="format",
            )
            append_diagnostic(results, location=location, details=details)
    return results


PHPLINT_PATTERN = re.compile(
    r"^Parse error: (?P<message>.+?) in (?P<file>.+) on line (?P<line>\d+)",
)


def parse_phplint(stdout: Sequence[str], context: ToolContext) -> Sequence[RawDiagnostic]:
    """Parse phplint textual output into diagnostics.

    Args:
        stdout: Sequence of phplint output lines using the standard format.
        context: Tool execution context supplied by the orchestrator.

    Returns:
        Sequence[RawDiagnostic]: Diagnostics describing parse errors reported by phplint.
    """

    del context
    results: list[RawDiagnostic] = []
    for raw_line in stdout:
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
            ),
        )
    return results


PERLCRITIC_PATTERN = re.compile(
    r"^(?P<file>[^:]+):(?P<line>\d+):(?P<column>\d+):\s*(?P<message>.+?)\s*\((?P<rule>[^)]+)\)$",
)


def parse_perlcritic(stdout: Sequence[str], context: ToolContext) -> Sequence[RawDiagnostic]:
    """Parse perlcritic textual output using the verbose template.

    Args:
        stdout: Sequence of perlcritic output lines.
        context: Tool execution context supplied by the orchestrator.

    Returns:
        Sequence[RawDiagnostic]: Diagnostics describing perlcritic findings.
    """

    del context
    results: list[RawDiagnostic] = []
    for raw_line in stdout:
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
            ),
        )
    return results


def parse_checkmake(payload: JsonValue, context: ToolContext) -> Sequence[RawDiagnostic]:
    """Parse checkmake JSON diagnostics into normalised objects.

    Args:
        payload: Parsed JSON payload emitted by checkmake.
        context: Tool execution context supplied by the orchestrator.

    Returns:
        Sequence[RawDiagnostic]: Diagnostics suitable for downstream processing.
    """
    del context
    results: list[RawDiagnostic] = []
    for entry in _iter_checkmake_entries(payload):
        file_path = entry.get("file") or entry.get("filename") or entry.get("name")
        issues = entry.get("errors") or entry.get("warnings") or entry.get("issues")
        for issue in iter_dicts(issues):
            diagnostic = _build_checkmake_diagnostic(file_path, issue)
            if diagnostic is not None:
                results.append(diagnostic)
    return results


def _build_checkmake_diagnostic(
    file_path: JsonValue | None,
    issue: Mapping[str, JsonValue],
) -> RawDiagnostic | None:
    """Return a normalised checkmake diagnostic when ``issue`` is valid.

    Args:
        file_path: File path associated with the diagnostic entry.
        issue: Mapping describing a single checkmake issue.

    Returns:
        RawDiagnostic | None: Diagnostic built from ``issue`` or ``None`` when invalid.
    """

    message = issue.get("message") or issue.get("description")
    if not message:
        return None
    rule = issue.get("rule") or issue.get("code")
    severity_label = issue.get("severity") or issue.get("level") or "warning"
    severity = map_severity(
        severity_label,
        CHECKMAKE_SEVERITY_MAP,
        Severity.WARNING,
    )
    path = str(file_path) if file_path else None
    location = DiagnosticLocation(
        file=path,
        line=coerce_optional_int(issue.get("line")),
        column=coerce_optional_int(issue.get("column") or issue.get("col")),
    )
    details = DiagnosticDetails(
        severity=severity,
        message=str(message).strip(),
        tool="checkmake",
        code=str(rule) if rule else None,
    )
    return create_spec(location=location, details=details).build()


def _iter_checkmake_entries(payload: JsonValue) -> tuple[Mapping[str, JsonValue], ...]:
    """Return checkmake file entries extracted from ``payload``.

    Args:
        payload: JSON payload emitted by checkmake.

    Returns:
        tuple[Mapping[str, JsonValue], ...]: Tuple containing per-file diagnostic entries.
    """

    if isinstance(payload, Mapping):
        candidates = payload.get("files") or payload.get("results")
        return tuple(mapping_sequence(candidates))
    return tuple(mapping_sequence(payload))


_CPPLINT_PATTERN = re.compile(
    r"""
    ^(?P<file>[^:]+):(?P<line>\d+):\s+
    (?P<message>.+?)\s+\[(?P<category>[^\]]+)\]\s+\[(?P<confidence>\d+)\]$
    """,
    re.VERBOSE,
)


def parse_cpplint(stdout: Sequence[str], context: ToolContext) -> Sequence[RawDiagnostic]:
    """Parse cpplint textual diagnostics into normalised objects.

    Args:
        stdout: Sequence of cpplint output lines.
        context: Tool execution context supplied by the orchestrator.

    Returns:
        Sequence[RawDiagnostic]: Diagnostics representing cpplint rule violations.
    """

    del context
    results: list[RawDiagnostic] = []
    for line in stdout:
        stripped = line.strip()
        if not stripped or stripped.startswith(
            ("Done processing", "Total errors"),
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
            ),
        )
    return results


def parse_shellcheck(payload: JsonValue, context: ToolContext) -> Sequence[RawDiagnostic]:
    """Parse shellcheck JSON payload into canonical diagnostics.

    Args:
        payload: Parsed JSON payload emitted by shellcheck.
        context: Tool execution context supplied by the orchestrator.

    Returns:
        Sequence[RawDiagnostic]: Diagnostics describing shellcheck findings.
    """

    del context
    diagnostics: list[RawDiagnostic] = []
    for entry in _iter_shellcheck_entries(payload):
        message = coerce_optional_str(entry.get("message"))
        if not message:
            continue
        severity = map_severity(
            entry.get("level"),
            SHELLCHECK_SEVERITY_MAP,
            Severity.WARNING,
        )
        location = DiagnosticLocation(
            file=coerce_optional_str(entry.get("file")),
            line=coerce_optional_int(entry.get("line")),
            column=coerce_optional_int(entry.get("column")),
        )
        details = DiagnosticDetails(
            severity=severity,
            message=message.strip(),
            tool="shellcheck",
            code=_format_shellcheck_code(entry.get("code")),
        )
        diagnostics.append(create_spec(location=location, details=details).build())
    return diagnostics


def _iter_shellcheck_entries(payload: JsonValue) -> tuple[Mapping[str, JsonValue], ...]:
    """Return shellcheck diagnostic entries regardless of payload shape."""

    if isinstance(payload, Mapping):
        comments = payload.get("comments")
        if comments is not None:
            return tuple(mapping_sequence(comments))
        return tuple(mapping_sequence(payload))
    return tuple(mapping_sequence(payload))


def _format_shellcheck_code(value: JsonValue | None) -> str | None:
    """Return shellcheck rule identifiers prefixed with ``SC``."""

    if value is None:
        return None
    if isinstance(value, int):
        return f"SC{value}"
    text = str(value).strip()
    if not text:
        return None
    try:
        numeric = int(text)
    except ValueError:
        return text
    return f"SC{numeric}"


_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*m")
_TOMBI_HEADER_RE = re.compile(
    r"^(?P<level>Error|Warning|Info|Hint|Note):\s*(?P<message>.+)$",
    re.IGNORECASE,
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


def parse_tombi(stdout: Sequence[str], context: ToolContext) -> Sequence[RawDiagnostic]:
    """Parse tombi textual diagnostics into canonical RawDiagnostic objects.

    Args:
        stdout: Sequence of tombi output lines containing ANSI highlighting.
        context: Tool execution context supplied by the orchestrator.

    Returns:
        Sequence[RawDiagnostic]: Diagnostics describing tombi lint findings.
    """

    del context
    cleaned = _ANSI_ESCAPE_RE.sub("", "\n".join(stdout))
    results: list[RawDiagnostic] = []
    for header, body in _split_tombi_blocks(cleaned.splitlines()):
        diagnostic = _build_tombi_diagnostic(header, body)
        if diagnostic is not None:
            results.append(diagnostic)
    return results


def _split_tombi_blocks(lines: Sequence[str]) -> tuple[tuple[str, list[str]], ...]:
    """Return (header, body) pairs for tombi diagnostic blocks.

    Args:
        lines: Sequence of tombi output lines stripped of ANSI escapes.

    Returns:
        tuple[tuple[str, list[str]], ...]: Tuple containing tombi diagnostic blocks.
    """

    current_header: str | None = None
    current_body: list[str] = []
    blocks: list[tuple[str, list[str]]] = []
    for raw_line in lines:
        line = raw_line.strip()
        header = _TOMBI_HEADER_RE.match(line)
        if header:
            if current_header is not None:
                blocks.append((current_header, current_body))
            current_header = line
            current_body = []
            continue
        if current_header is not None and line:
            current_body.append(line)
    if current_header is not None:
        blocks.append((current_header, current_body))
    return tuple(blocks)


def _build_tombi_diagnostic(header_line: str, body: Sequence[str]) -> RawDiagnostic | None:
    """Return a RawDiagnostic derived from a tombi block.

    Args:
        header_line: First line of the tombi block containing severity/message.
        body: Remaining lines describing location and supplemental context.

    Returns:
        RawDiagnostic | None: Diagnostic assembled from the block or ``None`` when parsing fails.
    """

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


def parse_golangci_lint(payload: JsonValue, context: ToolContext) -> Sequence[RawDiagnostic]:
    """Parse golangci-lint JSON output into raw diagnostics.

    Args:
        payload: Parsed JSON payload emitted by golangci-lint.
        context: Tool execution context supplied by the orchestrator.

    Returns:
        Sequence[RawDiagnostic]: Diagnostics reported by golangci-lint or its contributors.
    """
    del context
    results: list[RawDiagnostic] = []
    for issue in _iter_golangci_entries(payload):
        diagnostic = _build_golangci_diagnostic(issue)
        if diagnostic is not None:
            results.append(diagnostic)
    return results


def _iter_golangci_entries(payload: JsonValue) -> tuple[Mapping[str, JsonValue], ...]:
    """Return golangci-lint issue entries from ``payload``.

    Args:
        payload: JSON payload emitted by golangci-lint.

    Returns:
        tuple[Mapping[str, JsonValue], ...]: Tuple containing golangci-lint issues.
    """

    if isinstance(payload, Mapping):
        candidates = payload.get("Issues") or payload.get("issues")
        return tuple(mapping_sequence(candidates))
    return tuple(mapping_sequence(payload))


def _build_golangci_diagnostic(issue: Mapping[str, JsonValue]) -> RawDiagnostic | None:
    """Return a golangci-lint diagnostic when ``issue`` contains data.

    Args:
        issue: Mapping describing a single golangci-lint issue.

    Returns:
        RawDiagnostic | None: Diagnostic built from the issue or ``None`` when invalid.
    """

    position_value = issue.get("Pos") or issue.get("position")
    position = position_value if isinstance(position_value, Mapping) else {}
    path = position.get("Filename") or position.get("filename") or issue.get("file")
    message = str(issue.get("Text", "") or issue.get("text", "")).strip()
    if not message:
        return None
    severity_label = issue.get("Severity", "warning")
    severity = map_severity(
        severity_label,
        GOLANGCI_SEVERITY_MAP,
        Severity.WARNING,
    )
    sub_linter = issue.get("FromLinter") or issue.get("source") or "golangci-lint"
    code_value = issue.get("Code") or issue.get("code")
    location = DiagnosticLocation(
        file=str(path) if path else None,
        line=coerce_optional_int(position.get("Line") or position.get("line")),
        column=coerce_optional_int(position.get("Column") or position.get("column")),
    )
    details = DiagnosticDetails(
        severity=severity,
        message=message,
        tool=str(sub_linter),
        code=str(code_value) if code_value else None,
    )
    return create_spec(location=location, details=details).build()


def parse_cargo_clippy(payload: JsonValue, context: ToolContext) -> Sequence[RawDiagnostic]:
    """Parse Cargo Clippy JSON payloads into RawDiagnostic objects.

    Args:
        payload: JSON payload emitted by Cargo Clippy.
        context: Tool execution context supplied by the orchestrator.

    Returns:
        Sequence[RawDiagnostic]: Diagnostics representing Clippy findings.
    """

    del context
    results: list[RawDiagnostic] = []
    for record in mapping_sequence(payload):
        if record.get("reason") != CARGO_CLIPPY_DIAGNOSTIC_REASON:
            continue
        message_mapping = first_mapping(record.get("message"))
        level = str(message_mapping.get("level", "warning")).lower()
        spans = mapping_sequence(message_mapping.get("spans"))
        primary = next(
            (span for span in spans if span.get("is_primary")),
            spans[0] if spans else None,
        )
        file_name = coerce_optional_str(primary.get("file_name")) if primary else None
        line = coerce_optional_int(primary.get("line_start")) if primary else None
        column = coerce_optional_int(primary.get("column_start")) if primary else None
        code_mapping = first_mapping(message_mapping.get("code"))
        code = coerce_optional_str(code_mapping.get("code"))
        sev_enum = {
            "error": Severity.ERROR,
            "warning": Severity.WARNING,
            "note": Severity.NOTE,
            "help": Severity.NOTE,
        }.get(level, Severity.WARNING)
        results.append(
            RawDiagnostic(
                file=file_name,
                line=line,
                column=column,
                severity=sev_enum,
                message=(coerce_optional_str(message_mapping.get("message")) or "").strip(),
                code=code,
                tool="cargo-clippy",
            ),
        )
    return results


__all__ = [
    "parse_cargo_clippy",
    "parse_checkmake",
    "parse_cpplint",
    "parse_golangci_lint",
    "parse_perlcritic",
    "parse_phplint",
    "parse_shellcheck",
    "parse_shfmt",
    "parse_tombi",
]
