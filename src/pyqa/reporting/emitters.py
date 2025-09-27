# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Emit machine-readable reports for orchestrator results."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path

from ..annotations import HighlightKind
from ..models import Diagnostic, RunResult
from ..serialization import serialize_outcome
from ..severity import Severity, severity_to_sarif
from .advice import AdviceBuilder, AdviceEntry
from .concise_helpers import ConciseEntry, collect_entries_from_outcomes, resolve_root_path

SARIF_VERSION = "2.1.0"
SARIF_SCHEMA = "https://schemastore.azurewebsites.net/schemas/json/sarif-2.1.0.json"

_ADVICE_BUILDER = AdviceBuilder()
_ANNOTATION_ENGINE = _ADVICE_BUILDER.annotation_engine


def write_json_report(result: RunResult, path: Path) -> None:
    """Write a JSON report summarising tool outcomes."""
    payload = {
        "root": str(result.root),
        "files": [str(p) for p in result.files],
        "outcomes": [serialize_outcome(outcome) for outcome in result.outcomes],
        "analysis": result.analysis,
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
    tool_name: str,
    diagnostics: Sequence[Diagnostic],
    version: str | None,
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
            },
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
    include_advice: bool = False,
    advice_limit: int = 5,
    advice_template: str = "- **{category}:** {body}",
    advice_section_builder: Callable[[Sequence[AdviceEntry]], Sequence[str]] | None = None,
) -> None:
    """Render a Markdown summary for pull requests."""
    diagnostics: list[tuple[Diagnostic, str]] = []
    for outcome in result.outcomes:
        for diag in outcome.diagnostics:
            diagnostics.append((diag, outcome.tool))

    root_path = resolve_root_path(result.root)
    sanitized_lookup: dict[int, ConciseEntry] = {}
    for outcome in result.outcomes:
        entries_for_outcome = collect_entries_from_outcomes([outcome], root_path, deduplicate=False)
        for diag, entry in zip(outcome.diagnostics, entries_for_outcome, strict=False):
            sanitized_lookup[id(diag)] = entry

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
        ),
    )

    needs_advice = include_advice or "{advice" in template or "{advice" in advice_template
    needs_highlight = "{highlighted_message" in template

    advice_entries: list[AdviceEntry] = []
    advice_summary = ""
    advice_primary = ""
    advice_primary_category = ""
    advice_count = 0

    if needs_advice:
        advice_inputs = _diagnostics_to_advice_inputs(filtered, sanitized_lookup)
        advice_entries = _ADVICE_BUILDER.build(advice_inputs)
        advice_count = len(advice_entries)
        if advice_entries:
            limited = advice_entries[:advice_limit]
            advice_summary = "; ".join(f"{entry.category}: {entry.body}" for entry in limited)
            advice_primary_category = advice_entries[0].category
            advice_primary = advice_entries[0].body

    lines = ["# Lint Summary", ""]
    shown = 0
    for diag, tool in filtered:
        if shown >= limit:
            break
        entry = sanitized_lookup.get(id(diag))
        location = entry.file_path if entry else (diag.file or "<workspace>")
        if entry and entry.line_no >= 0:
            location += f":{entry.line_no}"
        elif diag.line is not None:
            location += f":{diag.line}"
            if diag.column is not None:
                location += f":{diag.column}"
        message_text = entry.message if entry else diag.message
        highlighted_message = _highlight_markdown(message_text) if needs_highlight else message_text
        entry = template.format(
            severity=diag.severity.value.upper(),
            tool=entry.tool_name if entry else tool,
            message=message_text,
            highlighted_message=highlighted_message,
            location=location,
            code=(entry.code if entry else (diag.code or "")),
            advice_summary=advice_summary,
            advice_primary=advice_primary,
            advice_primary_category=advice_primary_category,
            advice_count=advice_count,
        )
        lines.append(entry)
        shown += 1

    if len(filtered) > limit:
        lines.append("")
        lines.append(f"…and {len(filtered) - limit} more diagnostics.")

    if include_advice:
        section_lines: Sequence[str]
        if advice_section_builder is not None:
            section_lines = advice_section_builder(advice_entries)
        else:
            section_lines = _build_advice_section(advice_entries, advice_limit, advice_template)
        section_lines = list(section_lines)
        if section_lines:
            if lines[-1] != "":
                lines.append("")
            lines.extend(section_lines)

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


def _build_advice_section(
    advice_entries: Sequence[AdviceEntry],
    limit: int,
    template: str,
) -> list[str]:
    if not advice_entries:
        return []

    section: list[str] = ["", "## SOLID Advice", ""]
    for entry in advice_entries[:limit]:
        rendered = template.format(category=entry.category, body=entry.body)
        section.append(rendered)
    if len(advice_entries) > limit:
        section.append(f"- …and {len(advice_entries) - limit} more advice items.")
    return section


def _diagnostics_to_advice_inputs(
    diagnostics: Sequence[tuple[Diagnostic, str]],
    sanitized_lookup: dict[int, ConciseEntry] | None,
) -> list[tuple[str, int, str, str, str, str]]:
    entries: list[tuple[str, int, str, str, str, str]] = []
    for diag, tool in diagnostics:
        entry = sanitized_lookup.get(id(diag)) if sanitized_lookup else None
        file_path = entry.file_path if entry else (diag.file or "")
        line_no = entry.line_no if entry else (diag.line if diag.line is not None else -1)
        function = entry.function if entry else (diag.function or "")
        tool_name = entry.tool_name if entry else (diag.tool or tool or "").strip()
        code = entry.code if entry else ((diag.code or "-").strip() or "-")
        message = entry.message if entry else diag.message.splitlines()[0]
        entries.append((file_path, line_no, function, tool_name, code, message))
    return entries


def _highlight_markdown(message: str) -> str:
    spans = _ANNOTATION_ENGINE.message_spans(message)
    if not spans:
        return message
    spans = sorted(spans, key=lambda span: (span.start, span.end))
    wrappers: dict[HighlightKind, tuple[str, str]] = {
        "function": ("**`", "`**"),
        "class": ("**`", "`**"),
        "argument": ("`", "`"),
        "variable": ("`", "`"),
        "attribute": ("`", "`"),
        "file": ("`", "`"),
    }
    result: list[str] = []
    cursor = 0
    for span in spans:
        start, end = span.start, span.end
        if start < cursor:
            continue
        result.append(message[cursor:start])
        token = message[start:end]
        prefix, suffix = wrappers.get(span.kind or "argument", ("`", "`"))
        result.append(f"{prefix}{token}{suffix}")
        cursor = end
    result.append(message[cursor:])
    return "".join(result)
