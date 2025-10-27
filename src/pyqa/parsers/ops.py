# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Parsers for CI/CD and container tooling."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final

from pyqa.core.severity import Severity

from ..core.models import RawDiagnostic
from ..core.serialization import JsonValue, coerce_optional_int
from ..tools.base import ToolContext
from .base import (
    DiagnosticDetails,
    DiagnosticLocation,
    _coerce_dict_sequence,
    _coerce_object_mapping,
    _coerce_optional_str,
    append_raw_diagnostic,
    create_spec,
    iter_dicts,
    map_severity,
)


def parse_actionlint(payload: JsonValue, context: ToolContext) -> Sequence[RawDiagnostic]:
    """Parse actionlint JSON diagnostics into raw diagnostic objects.

    Args:
        payload: JSON payload emitted by actionlint.
        context: Tool execution context supplied by the orchestrator.

    Returns:
        Sequence[RawDiagnostic]: Normalised diagnostics describing actionable issues.
    """

    del context
    results: list[RawDiagnostic] = []
    for item in iter_dicts(payload):
        path = _coerce_optional_str(item.get("filepath") or item.get("path"))
        message = str(item.get("message", "")).strip()
        severity = item.get("severity", "error")
        code = item.get("kind")
        sev_enum = map_severity(severity, ACTIONLINT_SEVERITY_MAP, Severity.WARNING)
        location = DiagnosticLocation(
            file=path,
            line=coerce_optional_int(item.get("line")),
            column=coerce_optional_int(item.get("column")),
        )
        details = _build_actionlint_details(sev_enum, message, code)
        append_raw_diagnostic(
            results,
            spec=create_spec(location=location, details=details),
        )
    return results


def parse_kube_linter(payload: JsonValue, context: ToolContext) -> Sequence[RawDiagnostic]:
    """Parse kube-linter JSON diagnostics into raw diagnostic objects.

    Args:
        payload: JSON payload emitted by kube-linter.
        context: Tool execution context supplied by the orchestrator.

    Returns:
        Sequence[RawDiagnostic]: Diagnostics describing kube-linter findings.
    """

    del context
    reports: list[dict[str, JsonValue]] = []
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


def parse_dockerfilelint(payload: JsonValue, context: ToolContext) -> Sequence[RawDiagnostic]:
    """Parse dockerfilelint JSON output into raw diagnostic objects.

    Args:
        payload: JSON payload emitted by dockerfilelint.
        context: Tool execution context supplied by the orchestrator.

    Returns:
        Sequence[RawDiagnostic]: Diagnostics constructed from dockerfilelint issues.
    """

    del context
    results: list[RawDiagnostic] = []
    source = payload.get("files") if isinstance(payload, Mapping) else payload
    for entry in iter_dicts(source):
        file_path = _coerce_optional_str(entry.get("file"))
        issues = entry.get("issues")
        if not isinstance(issues, list):
            continue
        for issue in issues:
            if not isinstance(issue, dict):
                continue
            title = str(issue.get("title", "")).strip()
            description = str(issue.get("description", "")).strip()
            if title and description:
                message = f"{title}: {description}"
            elif title:
                message = title
            else:
                message = description
            if not message:
                continue
            results.append(
                RawDiagnostic(
                    file=file_path,
                    line=coerce_optional_int(issue.get("line")),
                    column=None,
                    severity=Severity.WARNING,
                    message=message,
                    code=str(issue.get("category")) if issue.get("category") else None,
                    tool="dockerfilelint",
                ),
            )
    return results


ACTIONLINT_SEVERITY_MAP: Final[dict[str, Severity]] = {
    "error": Severity.ERROR,
    "warning": Severity.WARNING,
    "note": Severity.NOTE,
}


def _build_actionlint_details(
    severity: Severity,
    message: str,
    code: JsonValue | None,
) -> DiagnosticDetails:
    """Return normalised actionlint diagnostic metadata.

    Args:
        severity: Severity derived from the actionlint entry.
        message: Human-readable diagnostic message.
        code: Optional rule identifier associated with the diagnostic.

    Returns:
        DiagnosticDetails: Metadata bundle describing the diagnostic.
    """

    rule = str(code) if code else None
    return DiagnosticDetails(
        severity=severity,
        message=message,
        tool="actionlint",
        code=rule,
    )
