# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Parsers for configuration and documentation tooling."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Final

from pyqa.core.serialization import JsonValue
from pyqa.core.severity import Severity

from ..core.models import RawDiagnostic
from ..tools.base import ToolContext
from .base import (
    DiagnosticDetails,
    DiagnosticLocation,
    append_diagnostic,
    create_spec,
    iter_dicts,
    iter_pattern_matches,
    map_severity,
)

DOTENV_PATTERN = re.compile(
    r"^(?P<file>[^:]+):(?P<line>\d+)\s+(?P<code>[A-Za-z0-9_-]+):\s+(?P<message>.+)$",
)
YAMLLINT_PATTERN = re.compile(
    r"^(?P<file>.*?):(?P<line>\d+):(?P<column>\d+):\s+\[(?P<level>[^\]]+)\]\s+"
    r"(?P<message>.*?)(?:\s+\((?P<rule>[^)]+)\))?$",
)
YAMLLINT_SEVERITY_MAP: Final[dict[str, Severity]] = {
    "error": Severity.ERROR,
    "warning": Severity.WARNING,
}
REMARK_SEVERITY_MAP: Final[dict[str, Severity]] = {
    "error": Severity.ERROR,
    "warning": Severity.WARNING,
    "info": Severity.NOTICE,
    "hint": Severity.NOTE,
}


def parse_sqlfluff(payload: JsonValue, context: ToolContext) -> Sequence[RawDiagnostic]:
    """Parse sqlfluff JSON diagnostics into raw diagnostic objects.

    Args:
        payload: JSON payload produced by sqlfluff.
        context: Tool execution context supplied by the orchestrator.

    Returns:
        Sequence[RawDiagnostic]: Normalised diagnostics ready for aggregation.
    """
    del context
    results: list[RawDiagnostic] = []
    for item in iter_dicts(payload):
        violations = item.get("violations")
        path = item.get("filepath")
        if not isinstance(violations, list):
            continue
        for violation in violations:
            if not isinstance(violation, dict):
                continue
            message = str(violation.get("description", "")).strip()
            code = violation.get("code")
            line = violation.get("line_no")
            column = violation.get("line_pos")
            severity = violation.get("severity", "error")
            sev_enum = map_severity(severity, SQLFLUFF_SEVERITY_MAP, Severity.WARNING)
            location = DiagnosticLocation(file=path, line=line, column=column)
            details = DiagnosticDetails(
                severity=sev_enum,
                message=message,
                tool="sqlfluff",
                code=str(code) if code else None,
            )
            results.append(create_spec(location=location, details=details).build())
    return results


def parse_yamllint(stdout: Sequence[str], context: ToolContext) -> Sequence[RawDiagnostic]:
    """Parse yamllint plain output into diagnostics.

    Args:
        stdout: Sequence of yamllint output lines.
        context: Tool execution context supplied by the orchestrator.

    Returns:
        Sequence[RawDiagnostic]: Diagnostics derived from yamllint findings.
    """

    del context
    results: list[RawDiagnostic] = []
    for match in iter_pattern_matches(stdout, YAMLLINT_PATTERN):
        file_path = match.group("file") or None
        line_text = match.group("line")
        column_text = match.group("column")
        message = (match.group("message") or "").strip()
        level = match.group("level") or "warning"
        rule = match.group("rule")

        severity = map_severity(level, YAMLLINT_SEVERITY_MAP, Severity.WARNING)

        location = DiagnosticLocation(
            file=file_path,
            line=int(line_text) if line_text else None,
            column=int(column_text) if column_text else None,
        )
        details = DiagnosticDetails(
            severity=severity,
            message=message,
            tool="yamllint",
            code=rule,
        )
        append_diagnostic(results, location=location, details=details)
    return results


def parse_dotenv_linter(stdout: Sequence[str], context: ToolContext) -> Sequence[RawDiagnostic]:
    """Parse dotenv-linter text output."""
    del context
    results: list[RawDiagnostic] = []
    for raw_line in stdout:
        line = raw_line.strip()
        if (
            not line
            or line.startswith("Checking")
            or line.startswith("Nothing to check")
            or line.startswith("No problems found")
        ):
            continue
        match = DOTENV_PATTERN.match(line)
        if not match:
            continue
        file_path = match.group("file")
        line_no = int(match.group("line")) if match.group("line") else None
        code = match.group("code")
        message = match.group("message").strip()
        results.append(
            RawDiagnostic(
                file=file_path,
                line=line_no,
                column=None,
                severity=Severity.WARNING,
                message=message,
                code=code,
                tool="dotenv-linter",
            ),
        )
    return results


def parse_remark(payload: JsonValue, context: ToolContext) -> Sequence[RawDiagnostic]:
    """Parse remark/remark-lint JSON output into raw diagnostics.

    Args:
        payload: JSON payload generated by remark or remark-lint.
        context: Tool execution context supplied by the orchestrator.

    Returns:
        Sequence[RawDiagnostic]: Diagnostics describing remark findings.
    """

    del context
    results: list[RawDiagnostic] = []
    for file_entry in _remark_file_entries(payload):
        file_path = _remark_file_path(file_entry)
        for message in _remark_messages(file_entry):
            diagnostic = _build_remark_diagnostic(file_path, message)
            if diagnostic is not None:
                results.append(diagnostic)
    return results


SPECCY_SEVERITY_MAP: Final[dict[str, Severity]] = {
    "error": Severity.ERROR,
    "warn": Severity.WARNING,
    "warning": Severity.WARNING,
    "info": Severity.NOTICE,
}


def parse_speccy(payload: JsonValue, context: ToolContext) -> Sequence[RawDiagnostic]:
    """Parse Speccy JSON output."""
    del context
    results: list[RawDiagnostic] = []
    for file_entry in _iter_speccy_files(payload):
        file_path = _speccy_file_path(file_entry)
        for severity_key, issue in _iter_speccy_issues(file_entry):
            message = _speccy_message(issue)
            if not message:
                continue
            severity = _speccy_severity(issue, severity_key)
            location = _speccy_location(issue)
            augmented_message = message if location is None else f"{location}: {message}"
            results.append(
                RawDiagnostic(
                    file=file_path,
                    line=None,
                    column=None,
                    severity=severity,
                    message=augmented_message,
                    code=issue.get("code") or issue.get("rule"),
                    tool="speccy",
                ),
            )
    return results


def _iter_speccy_files(payload: JsonValue) -> Iterable[Mapping[str, JsonValue]]:
    if isinstance(payload, list):
        return (item for item in payload if isinstance(item, Mapping))
    if isinstance(payload, Mapping):
        intermediate = payload.get("files") or payload.get("lint") or payload.get("results") or []
        return (item for item in intermediate if isinstance(item, Mapping))
    return ()


def _iter_speccy_issues(
    entry: Mapping[str, JsonValue],
) -> Iterable[tuple[str, Mapping[str, JsonValue]]]:
    issues = entry.get("issues") or entry.get("errors") or entry.get("problems") or []
    if isinstance(issues, Mapping):
        combined: list[tuple[str, Mapping[str, JsonValue]]] = []
        for key, value in issues.items():
            if isinstance(value, list):
                combined.extend((str(key), item) for item in value if isinstance(item, Mapping))
        return combined
    if isinstance(issues, list):
        return [("error", issue) for issue in issues if isinstance(issue, Mapping)]
    return ()


def _speccy_file_path(entry: Mapping[str, JsonValue]) -> str | None:
    value = entry.get("file") or entry.get("path") or entry.get("name")
    return str(value) if value else None


def _speccy_message(issue: Mapping[str, JsonValue]) -> str:
    primary = str(issue.get("message", "")).strip()
    if primary:
        return primary
    return str(issue.get("description", "")).strip()


def _speccy_severity(issue: Mapping[str, JsonValue], default_label: str) -> Severity:
    raw_label = issue.get("type") or issue.get("severity") or default_label or "warning"
    label = str(raw_label).strip().lower()
    return SPECCY_SEVERITY_MAP.get(label, Severity.WARNING)


def _speccy_location(issue: Mapping[str, JsonValue]) -> str | None:
    location = issue.get("location") or issue.get("path")
    if isinstance(location, list):
        return "/".join(str(part) for part in location)
    if location:
        return str(location)
    return None


def _remark_file_entries(payload: JsonValue) -> tuple[Mapping[str, JsonValue], ...]:
    """Return remark file entries extracted from ``payload``.

    Args:
        payload: Raw remark JSON payload.

    Returns:
        tuple[Mapping[str, Any], ...]: Iterable of mapping entries describing files.
    """

    if isinstance(payload, list):
        return tuple(entry for entry in payload if isinstance(entry, Mapping))
    if isinstance(payload, Mapping):
        intermediate = payload.get("files") or payload.get("results") or []
        return tuple(entry for entry in intermediate if isinstance(entry, Mapping))
    return ()


def _remark_messages(entry: Mapping[str, JsonValue]) -> tuple[Mapping[str, JsonValue], ...]:
    """Return message mappings contained within a remark file entry.

    Args:
        entry: Mapping describing a remark-processed file.

    Returns:
        tuple[Mapping[str, Any], ...]: Message mappings extracted from ``entry``.
    """

    messages = entry.get("messages")
    if isinstance(messages, list):
        return tuple(message for message in messages if isinstance(message, Mapping))
    return ()


def _remark_file_path(entry: Mapping[str, JsonValue]) -> str | None:
    """Return the file path associated with a remark entry when available.

    Args:
        entry: Mapping describing a remark-processed file.

    Returns:
        str | None: Resolved file path or ``None`` when absent.
    """

    value = entry.get("name") or entry.get("path") or entry.get("file")
    return str(value) if value else None


def _remark_severity(message: Mapping[str, JsonValue]) -> Severity:
    """Compute severity for a remark message mapping.

    Args:
        message: Mapping describing a single remark diagnostic entry.

    Returns:
        Severity: Severity inferred from the message content.
    """

    label = message.get("severity")
    if isinstance(label, str):
        return REMARK_SEVERITY_MAP.get(label.lower(), Severity.WARNING)
    fatal = message.get("fatal")
    return Severity.ERROR if bool(fatal) else Severity.WARNING


def _remark_location(message: Mapping[str, JsonValue]) -> tuple[int | None, int | None]:
    """Return best-effort location information for a remark message.

    Args:
        message: Mapping describing a single remark diagnostic entry.

    Returns:
        tuple[int | None, int | None]: Line and column numbers when available.
    """

    line = message.get("line")
    column = message.get("column")
    if line is not None or column is not None:
        return line, column
    location = message.get("location")
    if isinstance(location, Mapping):
        start = location.get("start")
        if isinstance(start, Mapping):
            start_line = start.get("line")
            start_column = start.get("column")
            return start_line, start_column
    return None, None


def _build_remark_diagnostic(
    file_path: str | None,
    message: Mapping[str, JsonValue],
) -> RawDiagnostic | None:
    """Return a raw diagnostic derived from a remark message mapping.

    Args:
        file_path: Path to the file associated with the remark message.
        message: Mapping describing a single remark diagnostic entry.

    Returns:
        RawDiagnostic | None: Normalised diagnostic or ``None`` when the message lacks content.
    """

    reason = str(message.get("reason", "")).strip()
    if not reason:
        return None
    severity = _remark_severity(message)
    line, column = _remark_location(message)
    rule = message.get("ruleId") or message.get("rule")
    return create_spec(
        location=DiagnosticLocation(file=file_path, line=line, column=column),
        details=DiagnosticDetails(
            severity=severity,
            message=reason,
            tool="remark-lint",
            code=str(rule) if rule else None,
        ),
    ).build()


__all__ = [
    "parse_dotenv_linter",
    "parse_remark",
    "parse_speccy",
    "parse_sqlfluff",
    "parse_yamllint",
]
SQLFLUFF_SEVERITY_MAP: Final[dict[str, Severity]] = {
    "error": Severity.ERROR,
    "critical": Severity.ERROR,
    "warn": Severity.WARNING,
    "warning": Severity.WARNING,
    "info": Severity.NOTICE,
}
