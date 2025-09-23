# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Emit machine-readable reports for orchestrator results."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Sequence

from ..models import Diagnostic, RunResult
from ..serialization import serialize_outcome
from ..severity import Severity, severity_to_sarif

SARIF_VERSION = "2.1.0"
SARIF_SCHEMA = "https://schemastore.azurewebsites.net/schemas/json/sarif-2.1.0.json"


def write_json_report(result: RunResult, path: Path) -> None:
    """Write a JSON report summarising tool outcomes."""

    payload = {
        "root": str(result.root),
        "files": [str(p) for p in result.files],
        "outcomes": [serialize_outcome(outcome) for outcome in result.outcomes],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_sarif_report(result: RunResult, path: Path) -> None:
    """Emit a SARIF document compatible with GitHub and other tools."""

    runs: list[dict[str, object]] = []
    for tool_name, diagnostics in _group_diagnostics_by_tool(result):
        version = result.tool_versions.get(tool_name)
        run = _build_sarif_run(tool_name, diagnostics, version)
        runs.append(run)

    sarif_doc = {
        "version": SARIF_VERSION,
        "$schema": SARIF_SCHEMA,
        "runs": runs,
    }
    path.write_text(json.dumps(sarif_doc, indent=2), encoding="utf-8")


def _build_sarif_run(
    tool_name: str, diagnostics: Sequence[Diagnostic], version: str | None
) -> dict[str, object]:
    """Construct the SARIF run dictionary for a single tool."""

    rules: dict[str, dict[str, object]] = {}
    results: list[dict[str, object]] = []

    for diag in diagnostics:
        rule_id = diag.code or tool_name
        if rule_id not in rules:
            rules[rule_id] = {
                "id": rule_id,
                "name": rule_id,
                "shortDescription": {"text": diag.message[:120]},
            }

        result_entry: dict[str, object] = {
            "ruleId": rule_id,
            "level": severity_to_sarif(diag.severity),
            "message": {"text": diag.message},
        }
        if diag.file:
            physical_location: dict[str, object] = {
                "artifactLocation": {"uri": diag.file},
            }
            region: dict[str, int] = {}
            if diag.line is not None:
                region["startLine"] = int(diag.line)
            if diag.column is not None:
                region["startColumn"] = int(diag.column)
            if region:
                physical_location["region"] = region
            result_entry["locations"] = [{"physicalLocation": physical_location}]
        results.append(result_entry)

    return {
        "tool": {
            "driver": {
                "name": tool_name,
                "version": version or "unknown",
                "rules": list(rules.values()) or None,
            }
        },
        "results": results,
    }


def write_pr_summary(
    result: RunResult,
    path: Path,
    *,
    limit: int = 100,
    min_severity: str = "warning",
    template: str = "- **{severity}** `{tool}` {message} ({location})",
) -> None:
    """Render a Markdown summary for pull requests."""

    diagnostics: list[tuple[Diagnostic, str]] = []
    for outcome in result.outcomes:
        for diag in outcome.diagnostics:
            diagnostics.append((diag, outcome.tool))

    severity_order = {
        Severity.ERROR: 0,
        Severity.WARNING: 1,
        Severity.NOTICE: 2,
        Severity.NOTE: 3,
    }

    min_rank = _severity_rank(min_severity, severity_order)

    filtered = [
        (diag, tool)
        for diag, tool in diagnostics
        if severity_order.get(diag.severity, 99) <= min_rank
    ]

    filtered.sort(
        key=lambda item: (
            severity_order.get(item[0].severity, 99),
            item[0].file or "",
            item[0].line or 0,
        )
    )

    lines = ["# Lint Summary", ""]
    shown = 0
    for diag, tool in filtered:
        if shown >= limit:
            break
        location = diag.file or "<workspace>"
        if diag.line is not None:
            location += f":{diag.line}"
            if diag.column is not None:
                location += f":{diag.column}"
        entry = template.format(
            severity=diag.severity.value.upper(),
            tool=tool,
            message=diag.message,
            location=location,
            code=diag.code or "",
        )
        lines.append(entry)
        shown += 1

    if len(filtered) > limit:
        lines.append("")
        lines.append(f"…and {len(filtered) - limit} more diagnostics.")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _group_diagnostics_by_tool(
    result: RunResult,
) -> Iterable[tuple[str, list[Diagnostic]]]:
    buckets: dict[str, list[Diagnostic]] = {}
    for outcome in result.outcomes:
        if not outcome.diagnostics:
            continue
        buckets.setdefault(outcome.tool, []).extend(outcome.diagnostics)
    return sorted(buckets.items(), key=lambda item: item[0])


def _severity_rank(value: str | Severity, mapping: dict[Severity, int]) -> int:
    if isinstance(value, Severity):
        return mapping.get(value, mapping[Severity.WARNING])
    normalized = str(value).strip().lower()
    for sev, rank in mapping.items():
        if sev.value == normalized:
            return rank
    return mapping[Severity.WARNING]
