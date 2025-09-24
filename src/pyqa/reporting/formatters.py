# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Console formatters for orchestrator results."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from ..config import OutputConfig
from ..logging import colorize, emoji
from ..metrics import (
    SUPPRESSION_LABELS,
    FileMetrics,
    compute_file_metrics,
    normalise_path_key,
)
from ..models import Diagnostic, RunResult
from ..severity import Severity


def render(result: RunResult, cfg: OutputConfig) -> None:
    if cfg.quiet:
        _render_quiet(result, cfg)
        return
    match cfg.output:
        case "pretty":
            _render_pretty(result, cfg)
        case "raw":
            _render_raw(result)
        case "concise" | _:
            _render_concise(result, cfg)


def _render_concise(result: RunResult, cfg: OutputConfig) -> None:
    root_path = Path(result.root)
    try:
        root_path = root_path.resolve()
    except OSError:
        pass

    total_actions = len(result.outcomes)
    failed_actions = sum(1 for outcome in result.outcomes if not outcome.ok)
    entries: set[tuple[str, int, str, str, str, str]] = set()
    for outcome in result.outcomes:
        for diag in outcome.diagnostics:
            tool_name = diag.tool or outcome.tool
            file_path = _normalize_concise_path(diag.file, root_path)
            line_no = diag.line if diag.line is not None else -1
            code = diag.code or "-"
            message = diag.message.splitlines()[0].strip() or "<no message provided>"
            function = diag.function or ""
            entries.add((file_path, line_no, function, tool_name, code, message))

    def sort_key(item: tuple[str, int, str, str, str, str]) -> tuple:
        file_path, line_no, function, tool_name, code, message = item
        return (
            file_path,
            line_no if line_no >= 0 else float("inf"),
            function,
            tool_name,
            code,
            message,
        )

    if entries:
        for file_path, line_no, function, tool_name, code, message in sorted(
            entries, key=sort_key
        ):
            location = file_path
            if line_no >= 0:
                location = f"{file_path}:{line_no}"
            if function:
                location = (
                    f"{location}:{function}"
                    if line_no >= 0
                    else f"{location}:{function}"
                )
            print(f"{tool_name}, {location}, {code}, {message}")

    diagnostics_count = len(entries)
    files_count = len(result.files)
    _emit_stats_line(result, cfg, diagnostics_count)

    symbol = "❌" if failed_actions else "✅"
    summary_symbol = emoji(symbol, cfg.emoji)
    summary_label = (
        f"{summary_symbol} {'Failed' if failed_actions else 'Passed'}"
        if summary_symbol
        else ("Failed" if failed_actions else "Passed")
    )
    summary_color = "red" if failed_actions else "green"
    stats_raw = (
        f"— {diagnostics_count} diagnostic(s) across {files_count} file(s); "
        f"{failed_actions} failing action(s) out of {total_actions}"
    )
    status_text = colorize(summary_label, summary_color, cfg.color)
    stats_text = colorize(stats_raw, "white", cfg.color)
    print(f"{status_text} {stats_text}".strip())


def _render_quiet(result: RunResult, cfg: OutputConfig) -> None:
    failed = [outcome for outcome in result.outcomes if not outcome.ok]
    if not failed:
        print("ok")
        return
    for outcome in failed:
        print(f"{outcome.tool}:{outcome.action} failed rc={outcome.returncode}")
        if outcome.stderr:
            print(outcome.stderr.rstrip())
        if outcome.diagnostics:
            _dump_diagnostics(outcome.diagnostics, cfg)


def _render_pretty(result: RunResult, cfg: OutputConfig) -> None:
    root_display = colorize(str(Path(result.root).resolve()), "blue", cfg.color)
    print(f"Root: {root_display}")
    for outcome in result.outcomes:
        status = (
            colorize("PASS", "green", cfg.color)
            if outcome.ok
            else colorize("FAIL", "red", cfg.color)
        )
        print(f"\n{outcome.tool}:{outcome.action} — {status}")
        if outcome.stdout:
            print(colorize("stdout:", "cyan", cfg.color))
            print(outcome.stdout.rstrip())
        if outcome.stderr:
            print(colorize("stderr:", "yellow", cfg.color))
            print(outcome.stderr.rstrip())
        if outcome.diagnostics:
            print(colorize("diagnostics:", "bold", cfg.color))
            _dump_diagnostics(outcome.diagnostics, cfg)

    if result.outcomes:
        print()
    _emit_stats_line(
        result, cfg, sum(len(outcome.diagnostics) for outcome in result.outcomes)
    )


def _render_raw(result: RunResult) -> None:
    for outcome in result.outcomes:
        print(outcome.stdout.rstrip())
        if outcome.stderr:
            print(outcome.stderr.rstrip())


def _normalize_concise_path(path_str: str | None, root: Path) -> str:
    if not path_str:
        return "<unknown>"
    candidate = Path(path_str)
    try:
        if candidate.is_absolute():
            try:
                candidate_resolved = candidate.resolve()
            except OSError:
                candidate_resolved = candidate
            try:
                root_resolved = root.resolve()
            except OSError:
                root_resolved = root
            try:
                return candidate_resolved.relative_to(root_resolved).as_posix()
            except ValueError:
                return candidate_resolved.as_posix()
        return candidate.as_posix()
    except OSError:
        return str(candidate)


def _dump_diagnostics(diags: Iterable[Diagnostic], cfg: OutputConfig) -> None:
    for diag in diags:
        location = ""
        if diag.file:
            suffix = ""
            if diag.line is not None:
                suffix = f":{diag.line}"
                if diag.column is not None:
                    suffix += f":{diag.column}"
            location = f"{diag.file}{suffix}"
        sev_color = _severity_color(diag.severity)
        sev_display = colorize(diag.severity.value, sev_color, cfg.color)
        code_display = f" [{diag.code}]" if diag.code else ""
        print(f"  {sev_display} {location} {diag.message}{code_display}")


def _severity_color(sev: Severity) -> str:
    return {
        Severity.ERROR: "red",
        Severity.WARNING: "yellow",
        Severity.NOTICE: "blue",
        Severity.NOTE: "cyan",
    }.get(sev, "yellow")


def _emit_stats_line(
    result: RunResult, cfg: OutputConfig, diagnostics_count: int
) -> None:
    metrics = _gather_metrics(result)
    loc_count = sum(metric.line_count for metric in metrics.values())
    suppression_counts = {
        label: sum(metric.suppressions.get(label, 0) for metric in metrics.values())
        for label in SUPPRESSION_LABELS
    }
    files_count = len(result.files)
    total_suppressions = sum(suppression_counts.values())
    detail_parts = [
        f"{count} {label}" for label, count in suppression_counts.items() if count
    ]
    suppression_text = (
        f"{total_suppressions} lint suppression{'s' if total_suppressions != 1 else ''}"
    )
    if detail_parts:
        suppression_text = f"{suppression_text} ({', '.join(detail_parts)})"
    warnings_per_loc = diagnostics_count / loc_count if loc_count else 0.0
    warnings_text = f"{warnings_per_loc:.3f} lint warnings per LoC"
    stats_components = [
        f"{files_count} file{'s' if files_count != 1 else ''}",
        f"{loc_count:,} LoC",
        suppression_text,
    ]
    stats_symbol = emoji("📊", cfg.emoji)
    prefix = f"{stats_symbol} " if stats_symbol else ""
    stats_label = colorize("stats:", "yellow", cfg.color)
    comma = colorize(", ", "white", cfg.color)
    body_parts: list[str] = []
    for index, component in enumerate(stats_components):
        body_parts.append(colorize(component, "orange", cfg.color))
        if index != len(stats_components) - 1:
            body_parts.append(comma)
    body = "".join(body_parts)
    warnings_colored = colorize(warnings_text, "orange", cfg.color)
    stats_line = f"{prefix}{stats_label} {body}   {warnings_colored}"
    print(stats_line)


def _gather_metrics(result: RunResult) -> dict[str, FileMetrics]:
    metrics: dict[str, FileMetrics] = {}
    seen: set[str] = set()
    for candidate in result.files:
        key = normalise_path_key(candidate)
        if key in seen:
            continue
        seen.add(key)
        metric = result.file_metrics.get(key)
        if metric is None:
            metric = compute_file_metrics(candidate)
        metric.ensure_labels()
        metrics[key] = metric
    return metrics
