# SPDX-License-Identifier: MIT
"""Parsers for CI/CD and container tooling."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ..models import RawDiagnostic
from ..severity import Severity
from ..tools.base import ToolContext
from .base import _coerce_dict_sequence, _coerce_object_mapping, _coerce_optional_str


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
            ),
        )
    return results


def parse_kube_linter(payload: Any, _context: ToolContext) -> Sequence[RawDiagnostic]:
    """Parse kube-linter JSON output."""
    reports: list[dict[str, object]] = []
    if isinstance(payload, dict):
        reports.extend(_coerce_dict_sequence(payload.get("Reports")))
    else:
        reports.extend(_coerce_dict_sequence(payload))

    diagnostics: list[RawDiagnostic] = []
    for report in reports:
        diagnostic_info = _coerce_object_mapping(report.get("Diagnostic"))
        message_raw = diagnostic_info.get("Message")
        message = str(message_raw).strip() if message_raw is not None else ""
        if not message:
            continue

        obj_info = _coerce_object_mapping(report.get("Object"))
        metadata = _coerce_object_mapping(obj_info.get("Metadata"))
        file_path = _coerce_optional_str(metadata.get("FilePath") or metadata.get("filePath"))

        diagnostics.append(
            RawDiagnostic(
                file=file_path,
                line=None,
                column=None,
                severity=Severity.ERROR,
                message=message,
                code=_coerce_optional_str(report.get("Check")),
                tool="kube-linter",
            ),
        )

    return diagnostics


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
            message = (
                title if description == "" else f"{title}: {description}" if title else description
            )
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
                ),
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
            ),
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
            ),
        )
    return results


__all__ = [
    "parse_actionlint",
    "parse_bandit",
    "parse_dockerfilelint",
    "parse_hadolint",
    "parse_kube_linter",
]
