# SPDX-License-Identifier: MIT
"""Parsers for configuration and documentation tooling."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Final

from ..models import RawDiagnostic
from ..severity import Severity
from ..tools.base import ToolContext

DOTENV_PATTERN = re.compile(
    r"^(?P<file>[^:]+):(?P<line>\d+)\s+(?P<code>[A-Za-z0-9_-]+):\s+(?P<message>.+)$",
)
YAMLLINT_PATTERN = re.compile(
    r"^(?P<file>.*?):(?P<line>\d+):(?P<column>\d+):\s+\[(?P<level>[^\]]+)\]\s+"
    r"(?P<message>.*?)(?:\s+\((?P<rule>[^)]+)\))?$",
)


def parse_sqlfluff(payload: Any, _context: ToolContext) -> Sequence[RawDiagnostic]:
    """Parse sqlfluff JSON diagnostics."""
    items = payload if isinstance(payload, list) else []
    results: list[RawDiagnostic] = []
    for item in items:
        if not isinstance(item, dict):
            continue
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
            severity = str(violation.get("severity", "error")).lower()
            sev_enum = {
                "error": Severity.ERROR,
                "critical": Severity.ERROR,
                "warn": Severity.WARNING,
                "warning": Severity.WARNING,
                "info": Severity.NOTICE,
            }.get(severity, Severity.WARNING)
            results.append(
                RawDiagnostic(
                    file=path,
                    line=line,
                    column=column,
                    severity=sev_enum,
                    message=message,
                    code=str(code) if code else None,
                    tool="sqlfluff",
                ),
            )
    return results


def parse_yamllint(stdout: str, _context: ToolContext) -> Sequence[RawDiagnostic]:
    """Parse yamllint parsable text output."""
    results: list[RawDiagnostic] = []
    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = YAMLLINT_PATTERN.match(line)
        if not match:
            continue
        file_path = match.group("file") or None
        line_no = int(match.group("line")) if match.group("line") else None
        column_no = int(match.group("column")) if match.group("column") else None
        message = match.group("message") or ""
        level = (match.group("level") or "warning").lower()
        rule = match.group("rule")

        severity = {
            "error": Severity.ERROR,
            "warning": Severity.WARNING,
        }.get(level, Severity.WARNING)

        results.append(
            RawDiagnostic(
                file=file_path,
                line=line_no,
                column=column_no,
                severity=severity,
                message=message.strip(),
                code=rule,
                tool="yamllint",
            ),
        )
    return results


def parse_dotenv_linter(stdout: str, _context: ToolContext) -> Sequence[RawDiagnostic]:
    """Parse dotenv-linter text output."""
    results: list[RawDiagnostic] = []
    for raw_line in stdout.splitlines():
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


def parse_remark(payload: Any, _context: ToolContext) -> Sequence[RawDiagnostic]:
    """Parse remark/remark-lint JSON output."""
    files: list[dict[str, Any]]
    if isinstance(payload, list):
        files = [item for item in payload if isinstance(item, dict)]
    elif isinstance(payload, dict):
        intermediate = payload.get("files") or payload.get("results") or []
        files = [item for item in intermediate if isinstance(item, dict)]
    else:
        files = []

    results: list[RawDiagnostic] = []
    for entry in files:
        file_path = entry.get("name") or entry.get("path") or entry.get("file")
        messages = entry.get("messages")
        if not isinstance(messages, list):
            continue
        for message in messages:
            if not isinstance(message, dict):
                continue
            reason = str(message.get("reason", "")).strip()
            if not reason:
                continue
            fatal = message.get("fatal")
            severity_label = message.get("severity")
            if isinstance(severity_label, str):
                severity = {
                    "error": Severity.ERROR,
                    "warning": Severity.WARNING,
                    "info": Severity.NOTICE,
                }.get(severity_label.lower(), Severity.WARNING)
            else:
                severity = Severity.ERROR if fatal in (True, 1) else Severity.WARNING

            line = message.get("line")
            column = message.get("column")
            location = message.get("location") if isinstance(message.get("location"), dict) else {}
            start = location.get("start") if isinstance(location, dict) else {}
            if line is None and isinstance(start, dict):
                line = start.get("line")
                column = start.get("column")

            results.append(
                RawDiagnostic(
                    file=file_path,
                    line=line,
                    column=column,
                    severity=severity,
                    message=reason,
                    code=message.get("ruleId") or message.get("rule"),
                    tool="remark-lint",
                ),
            )
    return results


SPECCY_SEVERITY_MAP: Final[dict[str, Severity]] = {
    "error": Severity.ERROR,
    "warn": Severity.WARNING,
    "warning": Severity.WARNING,
    "info": Severity.NOTICE,
}


def parse_speccy(payload: Any, _context: ToolContext) -> Sequence[RawDiagnostic]:
    """Parse Speccy JSON output."""
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


def _iter_speccy_files(payload: Any) -> Iterable[Mapping[str, Any]]:
    if isinstance(payload, list):
        return (item for item in payload if isinstance(item, Mapping))
    if isinstance(payload, Mapping):
        intermediate = payload.get("files") or payload.get("lint") or payload.get("results") or []
        return (item for item in intermediate if isinstance(item, Mapping))
    return ()


def _iter_speccy_issues(
    entry: Mapping[str, Any],
) -> Iterable[tuple[str, Mapping[str, Any]]]:
    issues = entry.get("issues") or entry.get("errors") or entry.get("problems") or []
    if isinstance(issues, Mapping):
        combined: list[tuple[str, Mapping[str, Any]]] = []
        for key, value in issues.items():
            if isinstance(value, list):
                combined.extend((str(key), item) for item in value if isinstance(item, Mapping))
        return combined
    if isinstance(issues, list):
        return [("error", issue) for issue in issues if isinstance(issue, Mapping)]
    return ()


def _speccy_file_path(entry: Mapping[str, Any]) -> str | None:
    value = entry.get("file") or entry.get("path") or entry.get("name")
    return str(value) if value else None


def _speccy_message(issue: Mapping[str, Any]) -> str:
    primary = str(issue.get("message", "")).strip()
    if primary:
        return primary
    return str(issue.get("description", "")).strip()


def _speccy_severity(issue: Mapping[str, Any], default_label: str) -> Severity:
    label = (
        (issue.get("type") or issue.get("severity") or default_label or "warning").strip().lower()
    )
    return SPECCY_SEVERITY_MAP.get(label, Severity.WARNING)


def _speccy_location(issue: Mapping[str, Any]) -> str | None:
    location = issue.get("location") or issue.get("path")
    if isinstance(location, list):
        return "/".join(str(part) for part in location)
    if location:
        return str(location)
    return None


__all__ = [
    "parse_dotenv_linter",
    "parse_remark",
    "parse_speccy",
    "parse_sqlfluff",
    "parse_yamllint",
]
