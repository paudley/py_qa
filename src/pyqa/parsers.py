"""Parsers that convert tool output into :class:`RawDiagnostic` instances."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Sequence

from .models import RawDiagnostic
from .severity import Severity, severity_from_code
from .tools.base import Parser, ToolContext

JsonTransform = Callable[[Any, ToolContext], Sequence[RawDiagnostic]]
TextTransform = Callable[[str, ToolContext], Sequence[RawDiagnostic]]


def _load_json_stream(stdout: str) -> Any:
    stdout = stdout.strip()
    if not stdout:
        return []
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        payload: list[Any] = []
        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                payload.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return payload


@dataclass(slots=True)
class JsonParser(Parser):
    """Parse stdout as JSON and delegate to a transform function."""

    transform: JsonTransform

    def parse(
        self, stdout: str, stderr: str, *, context: ToolContext
    ) -> Sequence[RawDiagnostic]:
        del stderr  # retain signature compatibility without using the value
        payload = _load_json_stream(stdout)
        return self.transform(payload, context)


@dataclass(slots=True)
class TextParser(Parser):
    """Parse stdout via text transformation function."""

    transform: TextTransform
    splitlines: bool = True

    def parse(
        self, stdout: str, stderr: str, *, context: ToolContext
    ) -> Sequence[RawDiagnostic]:
        del stderr
        return self.transform(stdout, context)


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
            )
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
        code = item.get("message-id") or item.get("symbol")
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
            )
        )
    return results


def parse_pyright(payload: Any, _context: ToolContext) -> Sequence[RawDiagnostic]:
    """Parse Pyright JSON diagnostics."""
    diagnostics = []
    if isinstance(payload, dict):
        diagnostics = payload.get("generalDiagnostics", []) or payload.get(
            "diagnostics", []
        )
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
            )
        )
    return results


def parse_mypy(payload: Any, _context: ToolContext) -> Sequence[RawDiagnostic]:
    """Parse MyPy JSON diagnostics."""
    items = payload if isinstance(payload, list) else []
    results: list[RawDiagnostic] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        path = item.get("path")
        message = str(item.get("message", "")).strip()
        severity = str(item.get("severity", "error")).lower()
        code = item.get("code") or item.get("error_code")
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
            )
        )
    return results


def parse_bandit(payload: Any, _context: ToolContext) -> Sequence[RawDiagnostic]:
    """Parse Bandit security findings."""
    if not isinstance(payload, dict):
        return []
    results: list[RawDiagnostic] = []
    for result in payload.get("results", []):
        if not isinstance(result, dict):
            continue
        path = result.get("filename")
        line = result.get("line_number")
        severity = str(result.get("issue_severity", "MEDIUM")).upper()
        sev_enum = {
            "HIGH": Severity.ERROR,
            "MEDIUM": Severity.WARNING,
            "LOW": Severity.NOTICE,
        }.get(severity, Severity.WARNING)
        results.append(
            RawDiagnostic(
                file=path,
                line=line,
                column=None,
                severity=sev_enum,
                message=str(result.get("issue_text", "")).strip(),
                code=result.get("test_id"),
                tool="bandit",
            )
        )
    return results


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
                )
            )
    return results


_TSC_PATTERN = re.compile(
    r"^(?P<file>[^:(\n]+)\((?P<line>\d+),(?P<col>\d+)\):\s*"
    r"(?P<severity>error|warning)\s*(?P<code>[A-Z]+\d+)?\s*:?\s*(?P<message>.+)$"
)


def parse_tsc(stdout: str, _context: ToolContext) -> Sequence[RawDiagnostic]:
    """Parse TypeScript compiler text diagnostics."""
    results: list[RawDiagnostic] = []
    for line in stdout.splitlines():
        match = _TSC_PATTERN.match(line.strip())
        if not match:
            continue
        severity = (
            Severity.ERROR if match.group("severity") == "error" else Severity.WARNING
        )
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
            )
        )
    return results


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
        results.append(
            RawDiagnostic(
                file=path,
                line=line,
                column=column,
                severity=sev_enum,
                message=str(issue.get("Text", "") or issue.get("text", "")).strip(),
                code=issue.get("FromLinter") or issue.get("source"),
                tool="golangci-lint",
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
    "JsonParser",
    "TextParser",
    "parse_ruff",
    "parse_pylint",
    "parse_pyright",
    "parse_mypy",
    "parse_bandit",
    "parse_eslint",
    "parse_tsc",
    "parse_golangci_lint",
    "parse_cargo_clippy",
]
