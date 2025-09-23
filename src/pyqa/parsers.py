# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
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

    def parse(self, stdout: str, stderr: str, *, context: ToolContext) -> Sequence[RawDiagnostic]:
        del stderr  # retain signature compatibility without using the value
        payload = _load_json_stream(stdout)
        return self.transform(payload, context)


@dataclass(slots=True)
class TextParser(Parser):
    """Parse stdout via text transformation function."""

    transform: TextTransform
    splitlines: bool = True

    def parse(self, stdout: str, stderr: str, *, context: ToolContext) -> Sequence[RawDiagnostic]:
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
        path = item.get("path") or item.get("file")
        message = str(item.get("message", "")).strip()
        severity = str(item.get("severity", "error")).lower()
        code = item.get("code") or item.get("error_code")
        function = item.get("function") or item.get("name") or item.get("target") or item.get("symbol")
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
            )
        )
    return results


def parse_actionlint(payload: Any, _context: ToolContext) -> Sequence[RawDiagnostic]:
    """Parse actionlint JSON diagnostics."""

    items = payload if isinstance(payload, list) else []
    results: list[RawDiagnostic] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        path = item.get("path")
        message = str(item.get("message", "")).strip()
        severity = str(item.get("severity", "error")).lower()
        code = item.get("kind")
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
                code=str(code) if code else None,
                tool="actionlint",
            )
        )
    return results


def parse_kube_linter(payload: Any, _context: ToolContext) -> Sequence[RawDiagnostic]:
    """Parse kube-linter JSON output."""

    reports: Iterable[dict[str, Any]]
    if isinstance(payload, dict):
        raw_reports = payload.get("Reports", [])
        reports = [item for item in raw_reports if isinstance(item, dict)]
    elif isinstance(payload, list):
        reports = [item for item in payload if isinstance(item, dict)]
    else:
        reports = []

    diagnostics: list[RawDiagnostic] = []
    for report in reports:
        diagnostic_info = report.get("Diagnostic") if isinstance(report.get("Diagnostic"), dict) else {}
        message = str(diagnostic_info.get("Message", "")).strip()
        if not message:
            continue

        obj_info = report.get("Object") if isinstance(report.get("Object"), dict) else {}
        metadata = obj_info.get("Metadata") if isinstance(obj_info, dict) else {}
        if not isinstance(metadata, dict):
            metadata = {}
        file_path = metadata.get("FilePath") or metadata.get("filePath")

        diagnostics.append(
            RawDiagnostic(
                file=file_path,
                line=None,
                column=None,
                severity=Severity.ERROR,
                message=message,
                code=str(report.get("Check")) if report.get("Check") else None,
                tool="kube-linter",
            )
        )

    return diagnostics


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
                )
            )
    return results


def parse_dockerfilelint(payload: Any, _context: ToolContext) -> Sequence[RawDiagnostic]:
    """Parse dockerfilelint JSON output."""

    files = []
    if isinstance(payload, dict):
        files = payload.get("files", [])
    elif isinstance(payload, list):
        files = payload

    results: list[RawDiagnostic] = []
    for entry in files:
        if not isinstance(entry, dict):
            continue
        file_path = entry.get("file")
        issues = entry.get("issues")
        if not isinstance(issues, list):
            continue
        for issue in issues:
            if not isinstance(issue, dict):
                continue
            title = str(issue.get("title", "")).strip()
            description = str(issue.get("description", "")).strip()
            message = title if description == "" else f"{title}: {description}" if title else description
            if not message:
                continue
            results.append(
                RawDiagnostic(
                    file=file_path,
                    line=int(issue.get("line", 0)) or None,
                    column=None,
                    severity=Severity.WARNING,
                    message=message,
                    code=str(issue.get("category")) if issue.get("category") else None,
                    tool="dockerfilelint",
                )
            )
    return results


LUALINT_PATTERN = re.compile(r"^(?P<file>[^:]+):(?P<line>\d+):\s*(?:\*\*\*\s*)?(?P<message>.+)$")


def parse_lualint(stdout: str, _context: ToolContext) -> Sequence[RawDiagnostic]:
    """Parse lualint text output."""

    results: list[RawDiagnostic] = []
    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("Usage"):
            continue
        match = LUALINT_PATTERN.match(line)
        if not match:
            continue
        results.append(
            RawDiagnostic(
                file=match.group("file"),
                line=int(match.group("line")),
                column=None,
                severity=Severity.WARNING,
                message=match.group("message").strip(),
                code=None,
                tool="lualint",
            )
        )
    return results


LUACHECK_PATTERN = re.compile(
    r"^(?P<file>[^:]+):(?P<line>\d+):(?P<column>\d+):\s+\((?P<code>[A-Z]\d+)\)\s+(?P<message>.+)$"
)


def parse_luacheck(stdout: str, _context: ToolContext) -> Sequence[RawDiagnostic]:
    """Parse luacheck plain formatter output."""

    results: list[RawDiagnostic] = []
    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("Total:"):
            continue
        match = LUACHECK_PATTERN.match(line)
        if not match:
            continue
        code = match.group("code")
        severity = Severity.ERROR if code.startswith("E") else Severity.WARNING
        results.append(
            RawDiagnostic(
                file=match.group("file"),
                line=int(match.group("line")),
                column=int(match.group("column")),
                severity=severity,
                message=match.group("message").strip(),
                code=code,
                tool="luacheck",
            )
        )
    return results


def parse_yamllint(payload: Any, _context: ToolContext) -> Sequence[RawDiagnostic]:
    """Parse yamllint JSON output."""

    items = payload if isinstance(payload, list) else []
    results: list[RawDiagnostic] = []
    for entry in items:
        if not isinstance(entry, dict):
            continue
        path = entry.get("file")
        problems = entry.get("problems") or entry.get("errors")
        if not isinstance(problems, list):
            continue
        for problem in problems:
            if not isinstance(problem, dict):
                continue
            message = str(problem.get("message", "")).strip()
            if not message:
                continue
            level = str(problem.get("level", "warning")).lower()
            severity = {
                "error": Severity.ERROR,
                "warning": Severity.WARNING,
            }.get(level, Severity.WARNING)
            results.append(
                RawDiagnostic(
                    file=path,
                    line=problem.get("line"),
                    column=problem.get("column"),
                    severity=severity,
                    message=message,
                    code=str(problem.get("rule")) if problem.get("rule") else None,
                    tool="yamllint",
                )
            )
    return results


def parse_hadolint(payload: Any, _context: ToolContext) -> Sequence[RawDiagnostic]:
    """Parse hadolint JSON output."""

    items = payload if isinstance(payload, list) else []
    results: list[RawDiagnostic] = []
    for entry in items:
        if not isinstance(entry, dict):
            continue
        message = str(entry.get("message", "")).strip()
        if not message:
            continue
        level = str(entry.get("level", "warning")).lower()
        severity = {
            "error": Severity.ERROR,
            "warning": Severity.WARNING,
            "info": Severity.NOTICE,
            "style": Severity.NOTE,
        }.get(level, Severity.WARNING)
        results.append(
            RawDiagnostic(
                file=entry.get("file"),
                line=entry.get("line"),
                column=entry.get("column"),
                severity=severity,
                message=message,
                code=str(entry.get("code")) if entry.get("code") else None,
                tool="hadolint",
            )
        )
    return results


DOTENV_PATTERN = re.compile(r"^(?P<file>[^:]+):(?P<line>\d+)\s+(?P<code>[A-Za-z0-9_-]+):\s+(?P<message>.+)$")


def parse_dotenv_linter(stdout: str, _context: ToolContext) -> Sequence[RawDiagnostic]:
    """Parse dotenv-linter text output."""

    results: list[RawDiagnostic] = []
    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("Checking") or line.startswith("Nothing to check") or line.startswith("No problems found"):
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
            )
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
    records = payload if isinstance(payload, list) else [payload] if isinstance(payload, dict) else []
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
    "parse_actionlint",
    "parse_sqlfluff",
    "parse_bandit",
    "parse_eslint",
    "parse_stylelint",
    "parse_dockerfilelint",
    "parse_lualint",
    "parse_luacheck",
    "parse_yamllint",
    "parse_hadolint",
    "parse_dotenv_linter",
    "parse_remark",
    "parse_tsc",
    "parse_golangci_lint",
    "parse_cargo_clippy",
]
