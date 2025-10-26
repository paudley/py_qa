# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Parsers for configuration and documentation tooling."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Final

from pyqa.core.serialization import JsonValue, coerce_optional_int, coerce_optional_str
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


def _mapping_sequence(value: JsonValue | None) -> tuple[Mapping[str, JsonValue], ...]:
    """Return mapping entries extracted from ``value`` when possible.

    Args:
        value: JSON payload that may contain mapping entries.

    Returns:
        tuple[Mapping[str, JsonValue], ...]: Tuple of mapping entries discovered in *value*.
    """

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(item for item in value if isinstance(item, Mapping))
    if isinstance(value, Mapping):
        return (value,)
    return ()


def _first_mapping(value: JsonValue | None) -> Mapping[str, JsonValue]:
    """Return ``value`` when it is a mapping, otherwise an empty mapping.

    Args:
        value: JSON payload that may contain mapping data.

    Returns:
        Mapping[str, JsonValue]: Extracted mapping or an empty mapping when absent.
    """

    return value if isinstance(value, Mapping) else {}


def parse_sqlfluff(payload: JsonValue, _context: ToolContext) -> Sequence[RawDiagnostic]:
    """Parse sqlfluff JSON diagnostics into raw diagnostic objects.

    Args:
        payload: JSON payload produced by sqlfluff.
        _context: Tool execution context supplied by the orchestrator (unused).

    Returns:
        Sequence[RawDiagnostic]: Normalised diagnostics ready for aggregation.
    """
    results: list[RawDiagnostic] = []
    for item in iter_dicts(payload):
        violations = item.get("violations")
        path_value = item.get("filepath")
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
            location = DiagnosticLocation(
                file=coerce_optional_str(path_value) if path_value is not None else None,
                line=coerce_optional_int(line) if line is not None else None,
                column=coerce_optional_int(column) if column is not None else None,
            )
            details = DiagnosticDetails(
                severity=sev_enum,
                message=message,
                tool="sqlfluff",
                code=coerce_optional_str(code) if code is not None else None,
            )
            results.append(create_spec(location=location, details=details).build())
    return results


def parse_yamllint(stdout: Sequence[str], _context: ToolContext) -> Sequence[RawDiagnostic]:
    """Parse yamllint plain output into diagnostics.

    Args:
        stdout: Sequence of yamllint output lines.
        _context: Tool execution context supplied by the orchestrator (unused).

    Returns:
        Sequence[RawDiagnostic]: Diagnostics derived from yamllint findings.
    """

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


def parse_dotenv_linter(stdout: Sequence[str], _context: ToolContext) -> Sequence[RawDiagnostic]:
    """Parse dotenv-linter text output into raw diagnostics.

    Args:
        stdout: Sequence of dotenv-linter output lines.
        _context: Tool execution context supplied by the orchestrator (unused).

    Returns:
        Sequence[RawDiagnostic]: Diagnostics describing dotenv-linter findings.
    """

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


def parse_remark(payload: JsonValue, _context: ToolContext) -> Sequence[RawDiagnostic]:
    """Parse remark/remark-lint JSON output into raw diagnostics.

    Args:
        payload: JSON payload generated by remark or remark-lint.
        _context: Tool execution context supplied by the orchestrator (unused).

    Returns:
        Sequence[RawDiagnostic]: Diagnostics describing remark findings.
    """
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


def parse_speccy(payload: JsonValue, _context: ToolContext) -> Sequence[RawDiagnostic]:
    """Parse Speccy JSON output into raw diagnostics.

    Args:
        payload: JSON payload emitted by Speccy.
        _context: Tool execution context supplied by the orchestrator (unused).

    Returns:
        Sequence[RawDiagnostic]: Diagnostics capturing Speccy-reported issues.
    """

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
            code_value = issue.get("code") or issue.get("rule")
            code_str = coerce_optional_str(code_value) if code_value is not None else None
            results.append(
                RawDiagnostic(
                    file=file_path,
                    line=None,
                    column=None,
                    severity=severity,
                    message=augmented_message,
                    code=code_str,
                    tool="speccy",
                ),
            )
    return results


def _iter_speccy_files(payload: JsonValue) -> Iterable[Mapping[str, JsonValue]]:
    """Return Speccy file entries extracted from ``payload``.

    Args:
        payload: JSON payload emitted by Speccy.

    Returns:
        Iterable[Mapping[str, JsonValue]]: Iterable of mapping entries describing files.
    """

    if isinstance(payload, Mapping):
        intermediate = payload.get("files") or payload.get("lint") or payload.get("results")
        return _mapping_sequence(intermediate)
    return _mapping_sequence(payload)


def _iter_speccy_issues(
    entry: Mapping[str, JsonValue],
) -> Iterable[tuple[str, Mapping[str, JsonValue]]]:
    """Return Speccy issues captured for a file entry.

    Args:
        entry: Mapping describing a Speccy file entry.

    Returns:
        Iterable[tuple[str, Mapping[str, JsonValue]]]: Iterable of (severity, issue) pairs.
    """

    issues = entry.get("issues") or entry.get("errors") or entry.get("problems")
    if isinstance(issues, Mapping):
        combined: list[tuple[str, Mapping[str, JsonValue]]] = []
        for key, value in issues.items():
            if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
                combined.extend((str(key), item) for item in value if isinstance(item, Mapping))
        return tuple(combined)
    return tuple(("error", issue) for issue in _mapping_sequence(issues))


def _speccy_file_path(entry: Mapping[str, JsonValue]) -> str | None:
    """Return the file path associated with a Speccy entry when available.

    Args:
        entry: Mapping describing a Speccy file entry.

    Returns:
        str | None: File path string or ``None`` when unavailable.
    """

    value = entry.get("file") or entry.get("path") or entry.get("name")
    return coerce_optional_str(value)


def _speccy_message(issue: Mapping[str, JsonValue]) -> str:
    """Return the primary diagnostic message for a Speccy issue.

    Args:
        issue: Mapping describing a Speccy issue entry.

    Returns:
        str: Diagnostic message extracted from ``issue``.
    """

    primary = str(issue.get("message", "")).strip()
    if primary:
        return primary
    return str(issue.get("description", "")).strip()


def _speccy_severity(issue: Mapping[str, JsonValue], default_label: str) -> Severity:
    """Return severity derived from a Speccy issue mapping.

    Args:
        issue: Mapping describing a Speccy issue entry.
        default_label: Severity label to fall back on when unspecified.

    Returns:
        Severity: Enum describing the computed severity.
    """

    raw_label = coerce_optional_str(issue.get("type")) or coerce_optional_str(issue.get("severity")) or default_label
    label = raw_label.strip().lower()
    return SPECCY_SEVERITY_MAP.get(label, Severity.WARNING)


def _speccy_location(issue: Mapping[str, JsonValue]) -> str | None:
    """Return location strings describing the Speccy issue path.

    Args:
        issue: Mapping describing a Speccy issue entry.

    Returns:
        str | None: Slash-delimited location string or ``None`` when absent.
    """

    location = issue.get("location") or issue.get("path")
    if isinstance(location, Sequence) and not isinstance(location, (str, bytes, bytearray)):
        parts = [coerce_optional_str(part) for part in location]
        return "/".join(part for part in parts if part)
    return coerce_optional_str(location)


def _remark_file_entries(payload: JsonValue) -> tuple[Mapping[str, JsonValue], ...]:
    """Return remark file entries extracted from ``payload``.

    Args:
        payload: Raw remark JSON payload.

    Returns:
        tuple[Mapping[str, JsonValue], ...]: Iterable of mapping entries describing files.
    """

    if isinstance(payload, Mapping):
        intermediate = payload.get("files") or payload.get("results")
        return _mapping_sequence(intermediate)
    return _mapping_sequence(payload)


def _remark_messages(entry: Mapping[str, JsonValue]) -> tuple[Mapping[str, JsonValue], ...]:
    """Return message mappings contained within a remark file entry.

    Args:
        entry: Mapping describing a remark-processed file.

    Returns:
        tuple[Mapping[str, JsonValue], ...]: Message mappings extracted from ``entry``.
    """

    return _mapping_sequence(entry.get("messages"))


def _remark_file_path(entry: Mapping[str, JsonValue]) -> str | None:
    """Return the file path associated with a remark entry when available.

    Args:
        entry: Mapping describing a remark-processed file.

    Returns:
        str | None: Resolved file path or ``None`` when absent.
    """

    value = entry.get("name") or entry.get("path") or entry.get("file")
    return coerce_optional_str(value)


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

    line = coerce_optional_int(message.get("line"))
    column = coerce_optional_int(message.get("column"))
    if line is not None or column is not None:
        return line, column
    start_mapping = _first_mapping(message.get("location")).get("start")
    start = _first_mapping(start_mapping)
    start_line = coerce_optional_int(start.get("line"))
    start_column = coerce_optional_int(start.get("column"))
    if start_line is not None or start_column is not None:
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
