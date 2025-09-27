# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Console formatters for orchestrator results."""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from pathlib import Path

from rich import box
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ..annotations import AnnotationEngine, MessageSpan
from ..config import OutputConfig
from ..console import console_manager
from ..logging import colorize, emoji
from ..metrics import (
    SUPPRESSION_LABELS,
    FileMetrics,
    compute_file_metrics,
    normalise_path_key,
)
from ..models import Diagnostic, RunResult
from ..severity import Severity
from .advice import AdviceEntry, generate_advice

_ANNOTATION_ENGINE = AnnotationEngine()
_CODE_TINT = "ansi256:105"
_LITERAL_TINT = "ansi256:208"


def render(result: RunResult, cfg: OutputConfig) -> None:
    _ANNOTATION_ENGINE.annotate_run(result)
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
    entries: list[tuple[str, int, str, str, str, str]] = []
    seen_exact: set[tuple[str, int, str, str, str, str]] = set()
    for outcome in result.outcomes:
        for diag in outcome.diagnostics:
            tool_name = diag.tool or outcome.tool
            file_path = _normalize_concise_path(diag.file, root_path)
            line_no = diag.line if diag.line is not None else -1
            raw_code = diag.code or "-"
            code = raw_code.strip() or "-"
            raw_message = diag.message.splitlines()[0]
            message = _clean_message(code, raw_message) or "<no message provided>"
            function = _normalise_symbol(diag.function)
            record = (file_path, line_no, function, tool_name, code, message)
            if record in seen_exact:
                continue
            seen_exact.add(record)
            entries.append(record)

    entries = _group_similar_messages(entries)

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

    formatted: list[tuple[str, str, str, str, str]] = []
    if entries:
        for file_path, line_no, function, tool_name, code, message in sorted(entries, key=sort_key):
            file_part = file_path
            suffix_parts: list[str] = []
            if line_no >= 0:
                suffix_parts.append(str(line_no))
            if function:
                suffix_parts.append(function)
            suffix = f":{':'.join(suffix_parts)}" if suffix_parts else ""
            formatted.append((tool_name, file_part, suffix, code, message))

    tool_padding_limit = 10
    raw_tool_width = max((len(item[0]) for item in formatted), default=0)
    tool_width = min(raw_tool_width, tool_padding_limit) if raw_tool_width else 0
    tint_tool = _tool_tinter(result, cfg)
    for tool_name, file_part, suffix, code, message in formatted:
        spacer = " " * max(tool_width - len(tool_name), 0) if tool_width else ""
        location = (file_part or "") + suffix
        location_display = _highlight_for_output(
            location,
            color=cfg.color,
            extra_spans=_location_function_spans(location),
        )
        message_display = _highlight_for_output(message, color=cfg.color)
        code_display = _format_code_value(code, cfg.color)
        print(f"{tint_tool(tool_name)}, {spacer}{location_display}, {code_display}, {message_display}")

    diagnostics_count = len(entries)
    files_count = len(result.files)
    if getattr(cfg, "advice", False):
        _render_advice(entries, cfg)
        _render_refactor_navigator(result, cfg)
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


def _tool_tinter(result: RunResult, cfg: OutputConfig) -> callable[[str], str]:
    if not cfg.color:
        return lambda tool: tool

    tools = sorted(
        {diag.tool or outcome.tool for outcome in result.outcomes for diag in outcome.diagnostics},
    )
    tint_map: dict[str, str] = {}
    palette = [255, 254, 253, 252, 251, 250, 249, 248]
    for index, tool_name in enumerate(tools):
        tint_map[tool_name or ""] = f"ansi256:{palette[index % len(palette)]}"

    def tint(tool: str) -> str:
        color = tint_map.get(tool)
        return colorize(tool, color, cfg.color) if color else tool

    return tint


def _normalise_symbol(value: str | None) -> str:
    if not value:
        return ""
    candidate = value.strip()
    if not candidate:
        return ""
    if "\n" in candidate:
        candidate = candidate.splitlines()[0].strip()
    if not candidate:
        return ""
    if candidate.startswith(("#", '"""', "'''")):
        return ""
    if any(char.isspace() for char in candidate):
        return ""
    allowed_symbols = {"_", ".", "-", ":", "<", ">", "[", "]", "(", ")"}
    if any(not ch.isalnum() and ch not in allowed_symbols for ch in candidate):
        return ""
    if len(candidate) > 80:
        candidate = f"{candidate[:77]}…"
    return candidate


def _collect_highlight_spans(text: str) -> list[MessageSpan]:
    return list(_ANNOTATION_ENGINE.message_spans(text))


def _location_function_spans(location: str) -> list[MessageSpan]:
    if ":" not in location:
        return []
    candidate = location.split(":")[-1].strip()
    if not candidate or not candidate.isidentifier():
        return []
    start = location.rfind(candidate)
    if start == -1:
        return []
    return [MessageSpan(start=start, end=start + len(candidate), style="ansi256:208")]


def _apply_highlighting_text(message: str, base_style: str | None = None) -> Text:
    clean = message.replace("`", "")
    clean, literal_spans = _strip_literal_quotes(clean)
    text = Text(clean)
    if base_style:
        text.stylize(base_style, 0, len(text))
    spans = list(_collect_highlight_spans(clean))
    spans.extend(literal_spans)
    spans.sort(key=lambda span: (span.start, span.end))
    for span in spans:
        text.stylize(span.style, span.start, span.end)
    return text


def _highlight_for_output(message: str, *, color: bool, extra_spans: Sequence[MessageSpan] | None = None) -> str:
    clean = message.replace("`", "")
    if not color:
        clean, _ = _strip_literal_quotes(clean)
        return clean
    clean, literal_spans = _strip_literal_quotes(clean)
    spans = list(_collect_highlight_spans(clean))
    spans.extend(literal_spans)
    if extra_spans:
        spans.extend(extra_spans)
    if not spans:
        return clean
    spans.sort(key=lambda span: (span.start, span.end - span.start))
    merged: list[MessageSpan] = []
    for span in spans:
        if merged and span.start < merged[-1].end:
            continue
        merged.append(span)
    result: list[str] = []
    cursor = 0
    for span in merged:
        start, end, style = span.start, span.end, span.style
        if start < cursor:
            continue
        result.append(clean[cursor:start])
        token = clean[start:end]
        result.append(colorize(token, style, color))
        cursor = end
    result.append(clean[cursor:])
    return "".join(result)


def _infer_annotation_targets(message: str) -> int:
    spans = _ANNOTATION_ENGINE.message_spans(message)
    return sum(1 for span in spans if span.style == "ansi256:213")


_MERGEABLE_MESSAGE = re.compile(r"^(?P<prefix>.*?)(`(?P<detail>[^`]+)`)(?P<suffix>.*)$")


def _group_similar_messages(
    entries: list[tuple[str, int, str, str, str, str]],
) -> list[tuple[str, int, str, str, str, str]]:
    grouped: dict[
        tuple[str, int, str, str, str, str, str],
        dict[str, object],
    ] = {}
    ordered_keys: list[tuple[str, int, str, str, str, str, str]] = []

    for file_path, line_no, function, tool_name, code, message in entries:
        match = _MERGEABLE_MESSAGE.match(message)
        if not match:
            sanitized_message = message.replace("`", "")
            grouped_key = (file_path, line_no, function, tool_name, code, sanitized_message, "")
            if grouped_key not in grouped:
                grouped[grouped_key] = {
                    "prefix": sanitized_message,
                    "suffix": "",
                    "details": [],
                    "message": sanitized_message,
                }
                ordered_keys.append(grouped_key)
            continue

        prefix = match.group("prefix").replace("`", "")
        detail = match.group("detail").replace("`", "")
        suffix = match.group("suffix").replace("`", "")
        if not detail:
            grouped_key = (file_path, line_no, function, tool_name, code, prefix + suffix, "")
            if grouped_key not in grouped:
                grouped[grouped_key] = {
                    "prefix": prefix,
                    "suffix": "",
                    "details": [],
                    "message": (prefix + suffix).strip(),
                }
                ordered_keys.append(grouped_key)
            continue

        grouped_key = (file_path, line_no, function, tool_name, code, prefix, suffix)
        bucket = grouped.get(grouped_key)
        if bucket is None:
            bucket = {
                "prefix": prefix,
                "suffix": suffix,
                "details": [],
                "message": (prefix + detail + suffix).strip(),
            }
            grouped[grouped_key] = bucket
            ordered_keys.append(grouped_key)
        details: list[str] = bucket["details"]  # type: ignore[assignment]
        if detail not in details:
            details.append(detail)

    merged: list[tuple[str, int, str, str, str, str]] = []
    for grouped_key in ordered_keys:
        file_path, line_no, function, tool_name, code, prefix, suffix = grouped_key
        bucket = grouped[grouped_key]
        details: list[str] = bucket["details"]  # type: ignore[assignment]
        if not details or len(details) == 1:
            message = bucket["message"]  # type: ignore[assignment]
        else:
            joined = ", ".join(details)
            message = f"{prefix}{joined}{suffix}".strip()
        merged.append((file_path, line_no, function, tool_name, code, message.replace("`", "")))
    return merged


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
        status = colorize("PASS", "green", cfg.color) if outcome.ok else colorize("FAIL", "red", cfg.color)
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
    _emit_stats_line(result, cfg, sum(len(outcome.diagnostics) for outcome in result.outcomes))


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
    collected = list(diags)
    if not collected:
        return

    locations: list[str] = []
    for diag in collected:
        location = ""
        if diag.file:
            suffix = ""
            if diag.line is not None:
                suffix = f":{diag.line}"
                if diag.column is not None:
                    suffix += f":{diag.column}"
            location = f"{diag.file}{suffix}"
        locations.append(location)

    location_width = max((len(loc) for loc in locations), default=0)

    for diag, location in zip(collected, locations, strict=False):
        sev_color = _severity_color(diag.severity)
        sev_display = colorize(diag.severity.value, sev_color, cfg.color)
        code_value = (diag.code or "").strip()
        code_display = f" [{_format_code_value(code_value, cfg.color)}]" if code_value else ""
        padded_location = location.ljust(location_width) if location_width else location
        padding = " " if padded_location else ""
        message = _clean_message(code_value, diag.message)
        location_display = _highlight_for_output(
            padded_location,
            color=cfg.color,
            extra_spans=_location_function_spans(location),
        )
        message_display = _highlight_for_output(message, color=cfg.color)
        print(f"  {sev_display} {location_display}{padding}{message_display}{code_display}")


def _severity_color(sev: Severity) -> str:
    return {
        Severity.ERROR: "red",
        Severity.WARNING: "yellow",
        Severity.NOTICE: "blue",
        Severity.NOTE: "cyan",
    }.get(sev, "yellow")


def _clean_message(code: str | None, message: str) -> str:
    if not message:
        return message

    first_line, newline, remainder = message.partition("\n")
    working = first_line.lstrip()
    normalized_code = (code or "").strip()

    if normalized_code and normalized_code != "-":
        patterns = [
            f"{normalized_code}: ",
            f"{normalized_code}:",
            f"{normalized_code} - ",
            f"{normalized_code} -",
            f"{normalized_code} ",
            f"[{normalized_code}] ",
            f"[{normalized_code}]",
        ]
        for pattern in patterns:
            if working.startswith(pattern):
                working = working[len(pattern) :]
                break
        else:
            working = working.removeprefix(normalized_code)

    cleaned_first = working.lstrip()
    if newline:
        return cleaned_first + "\n" + remainder
    return cleaned_first


def _emit_stats_line(result: RunResult, cfg: OutputConfig, diagnostics_count: int) -> None:
    if not cfg.show_stats:
        return
    metrics = _gather_metrics(result)
    loc_count = sum(metric.line_count for metric in metrics.values())
    suppression_counts = {
        label: sum(metric.suppressions.get(label, 0) for metric in metrics.values()) for label in SUPPRESSION_LABELS
    }
    files_count = len(result.files)
    total_suppressions = sum(suppression_counts.values())
    warnings_per_loc = diagnostics_count / loc_count if loc_count else 0.0
    console = console_manager.get(color=cfg.color, emoji=cfg.emoji)

    table = Table(
        show_header=False,
        box=box.SIMPLE,
        pad_edge=False,
        expand=False,
    )
    label_style = "yellow" if cfg.color else None
    value_style = "orange1" if cfg.color else None

    def styled(value: str, style: str | None) -> Text:
        return Text(value, style=style) if style else Text(value)

    table.add_column(style=label_style, justify="left", no_wrap=True)
    table.add_column(style=value_style, justify="right", no_wrap=True)

    table.add_row(
        styled("Files", label_style),
        styled(f"{files_count}", value_style),
    )
    table.add_row(
        styled("Lines of code", label_style),
        styled(f"{loc_count:,}", value_style),
    )
    table.add_row(
        styled("Lint suppressions", label_style),
        styled(str(total_suppressions), value_style),
    )
    for label in SUPPRESSION_LABELS:
        table.add_row(
            styled(f"- {label} suppressions", label_style),
            styled(str(suppression_counts[label]), value_style),
        )
    table.add_row(
        styled("Warnings / LoC", label_style),
        styled(f"{warnings_per_loc:.3f}", value_style),
    )

    title_text = "stats"
    if cfg.emoji:
        title_text = f"📊 {title_text}"
    title = title_text if not cfg.color else f"[yellow]{title_text}[/yellow]"
    panel = Panel.fit(
        table,
        title=title,
        padding=(0, 1),
    )
    if cfg.color:
        panel.border_style = "yellow"
    console.print(panel)


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


def _render_advice(
    entries: Iterable[tuple[str, int, str, str, str, str]],
    cfg: OutputConfig,
) -> None:
    if not entries:
        return

    advice_entries = generate_advice(list(entries), _ANNOTATION_ENGINE)
    if not advice_entries:
        return

    console = console_manager.get(color=cfg.color, emoji=cfg.emoji)

    def stylise(entry: AdviceEntry) -> Text:
        if not cfg.color:
            return Text(f"{entry.category}: {entry.body}")
        prefix = Text(f"{entry.category}: ", style="bold yellow")
        rest_text = _apply_highlighting_text(entry.body)
        return prefix + rest_text

    body = Text()
    for idx, entry in enumerate(advice_entries):
        line = stylise(entry)
        if cfg.color:
            line = Text.from_markup(line.plain if isinstance(line, Text) else str(line))
        if idx:
            body.append("\n")
        line.no_wrap = False
        body.append(line)

    panel = Panel(
        body,
        title="SOLID Advice",
        border_style="cyan" if cfg.color else "none",
        padding=(0, 1),
    )
    console.print(panel)


def _render_refactor_navigator(result: RunResult, cfg: OutputConfig) -> None:
    navigator = result.analysis.get("refactor_navigator")
    if not navigator:
        return

    console = console_manager.get(color=cfg.color, emoji=cfg.emoji)
    table = Table(box=box.SIMPLE_HEAVY if cfg.color else box.SIMPLE)
    table.add_column("Function", overflow="fold")
    table.add_column("Issues", justify="right")
    table.add_column("Tags", overflow="fold")
    table.add_column("Size", justify="right")
    table.add_column("Complexity", justify="right")

    for entry in navigator[:5]:
        function = entry.get("function") or "<module>"
        file_path = entry.get("file") or ""
        location = f"{file_path}:{function}" if file_path else function
        issues = sum(int(value) for value in entry.get("issue_tags", {}).values())
        tags = ", ".join(sorted(entry.get("issue_tags", {}).keys()))
        size = entry.get("size")
        complexity = entry.get("complexity")
        table.add_row(
            location,
            str(issues),
            tags or "-",
            "-" if size is None else str(size),
            "-" if complexity is None else str(complexity),
        )

    panel = Panel(
        table,
        title="Refactor Navigator",
        border_style="magenta" if cfg.color else "none",
    )
    console.print(panel)


_CODE_TINT = "ansi256:105"


def _format_code_value(code: str, color_enabled: bool) -> str:
    clean = code.strip() or "-"
    if clean == "-":
        return clean
    return colorize(clean, _CODE_TINT, color_enabled)


def _strip_literal_quotes(text: str) -> tuple[str, list[MessageSpan]]:
    segments: list[str] = []
    spans: list[MessageSpan] = []
    cursor = 0
    out_len = 0
    length = len(text)
    while cursor < length:
        start = text.find("''", cursor)
        if start == -1:
            segments.append(text[cursor:])
            break
        segments.append(text[cursor:start])
        out_len += start - cursor
        end = text.find("''", start + 2)
        if end == -1:
            segments.append(text[start:])
            break
        literal = text[start + 2 : end]
        segments.append(literal)
        literal_length = len(literal)
        if literal_length:
            spans.append(
                MessageSpan(
                    start=out_len,
                    end=out_len + literal_length,
                    style=_LITERAL_TINT,
                ),
            )
        out_len += literal_length
        cursor = end + 2
    new_text = "".join(segments)
    return new_text, spans
