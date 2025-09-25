# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Console formatters for orchestrator results."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from pathlib import Path

from rich import box
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

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

_DUPLICATE_HINT_CODES: dict[str, set[str]] = {
    "pylint": {"R0801"},
    "ruff": {
        "B014",
        "B025",
        "B033",
        "PIE794",
        "PIE796",
        "PYI016",
        "PYI062",
        "PT014",
        "SIM101",
        "PLE0241",
        "PLE1132",
        "PLE1310",
        "PLR0804",
    },
}


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
        location_display = _highlight_for_output(location, color=cfg.color)
        message_display = _highlight_for_output(message, color=cfg.color)
        print(f"{tint_tool(tool_name)}, {spacer}{location_display}, {code}, {message_display}")

    diagnostics_count = len(entries)
    files_count = len(result.files)
    if getattr(cfg, "advice", False):
        _render_advice(entries, cfg)
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


def _summarise_paths(paths: Sequence[str], *, limit: int = 5) -> str:
    if not paths:
        return ""
    shown = [path for path in paths[:limit]]
    summary = ", ".join(shown)
    remainder = len(paths) - len(shown)
    if remainder > 0:
        summary = f"{summary}, ... (+{remainder} more)"
    return summary


def _estimate_function_scale(path: Path, function: str) -> tuple[int | None, int | None]:
    if not function:
        return (None, None)
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return (None, None)
    lines = text.splitlines()
    pattern = re.compile(rf"^\s*(?:async\s+)?def\s+{re.escape(function)}\b")
    start_index: int | None = None
    indent_level: int | None = None
    for idx, line in enumerate(lines):
        if pattern.match(line):
            start_index = idx
            indent_level = len(line) - len(line.lstrip(" \t"))
            break
    if start_index is None or indent_level is None:
        return (None, None)

    count = 1  # include signature
    complexity = 0
    keywords = re.compile(r"\b(if|for|while|elif|case|except|and|or|try|with)\b")
    for line in lines[start_index + 1 :]:
        stripped = line.strip()
        if not stripped:
            continue
        current_indent = len(line) - len(line.lstrip(" \t"))
        if current_indent <= indent_level:
            break
        count += 1
        complexity += len(keywords.findall(stripped))
    return (count if count else None, complexity if complexity else None)


_FILE_HIGHLIGHT = "ansi256:81"  # vivid cyan
_FUNCTION_HIGHLIGHT = "ansi256:208"  # warm orange
_CLASS_HIGHLIGHT = "ansi256:154"  # bright green
_ARG_HIGHLIGHT = "ansi256:213"  # soft magenta
_VAR_HIGHLIGHT = "ansi256:156"  # mint

_PATH_PATTERN = re.compile(
    r"((?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+(?:\.[A-Za-z0-9_]+)?|[A-Za-z0-9_.-]+\.[A-Za-z0-9_]+)",
)
_CLASS_PATTERN = re.compile(r"\b([A-Z][A-Za-z0-9]+(?:[A-Z][A-Za-z0-9]+)+)\b")
_FUNCTION_PATTERN = re.compile(
    r"\bfunction\s+(?!argument\b|parameter\b)([A-Za-z_][\w\.]+)",
    re.IGNORECASE,
)
_FUNCTION_INLINE_PATTERN = re.compile(
    r"\b(?!argument\b|parameter\b)([A-Za-z_][\w\.]+)\s+in\s+(?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+(?:\.[A-Za-z0-9_]+)?",
    re.IGNORECASE,
)
_ARGUMENT_PATTERN = re.compile(r"\b(?:argument|parameter)\s+([A-Za-z_][\w\.]+)", re.IGNORECASE)
_VARIABLE_PATTERN = re.compile(r"\bvariable(?:\s+name)?\s+([A-Za-z_][\w\.]+)", re.IGNORECASE)
_ATTRIBUTE_PATTERN = re.compile(r"attribute\s+[\"']([A-Za-z_][\w\.]*)[\"']", re.IGNORECASE)

_HIGHLIGHT_PATTERNS: tuple[tuple[re.Pattern[str], int, str], ...] = (
    (_PATH_PATTERN, 0, _FILE_HIGHLIGHT),
    (_CLASS_PATTERN, 1, _CLASS_HIGHLIGHT),
    (_FUNCTION_PATTERN, 1, _FUNCTION_HIGHLIGHT),
    (_FUNCTION_INLINE_PATTERN, 1, _FUNCTION_HIGHLIGHT),
    (_ARGUMENT_PATTERN, 1, _ARG_HIGHLIGHT),
    (_VARIABLE_PATTERN, 1, _VAR_HIGHLIGHT),
    (_ATTRIBUTE_PATTERN, 1, _FUNCTION_HIGHLIGHT),
)

_ANNOTATION_ARG_PATTERNS = (
    re.compile(r"function argument(?:s)?\s+([A-Za-z0-9_,\s]+)", re.IGNORECASE),
    re.compile(r"function parameter(?:s)?\s+([A-Za-z0-9_,\s]+)", re.IGNORECASE),
    re.compile(r"parameter(?:s)?\s+([A-Za-z0-9_,\s]+)", re.IGNORECASE),
)


def _collect_highlight_spans(text: str) -> list[tuple[int, int, str]]:
    spans: list[tuple[int, int, str]] = []
    for pattern, group_index, style in _HIGHLIGHT_PATTERNS:
        for match in pattern.finditer(text):
            try:
                segment = match.group(group_index)
                base = match.start(group_index)
            except IndexError:
                segment = match.group(0)
                base = match.start(0)

            if style == _ARG_HIGHLIGHT:
                offset = 0
                for part in segment.split(","):
                    name = part.strip(" \t.:;'\"")
                    if not name:
                        offset += len(part) + 1
                        continue
                    local_start = segment.find(name, offset)
                    offset = local_start + len(name)
                    start = base + local_start
                    end = start + len(name)
                    spans.append((start, end, style))
                continue

            if style == _VAR_HIGHLIGHT:
                name = segment.strip(" \t.:;'\"")
                if not name:
                    continue
                start = base + segment.find(name)
                end = start + len(name)
                spans.append((start, end, style))
                continue

            spans.append((base, base + len(segment), style))
    spans.sort(key=lambda item: (item[0], -(item[1] - item[0])))
    filtered: list[tuple[int, int, str]] = []
    last_end = -1
    for start, end, style in spans:
        if start < last_end:
            continue
        filtered.append((start, end, style))
        last_end = end
    return filtered


def _apply_highlighting_text(message: str, base_style: str | None = "white") -> Text:
    clean = message.replace("`", "")
    text = Text(clean)
    if base_style:
        text.stylize(base_style, 0, len(text))
    for start, end, style in _collect_highlight_spans(clean):
        text.stylize(style, start, end)
    return text


def _highlight_for_output(message: str, *, color: bool) -> str:
    clean = message.replace("`", "")
    if not color:
        return clean
    spans = _collect_highlight_spans(clean)
    if not spans:
        return clean
    result: list[str] = []
    cursor = 0
    for start, end, style in spans:
        if start < cursor:
            continue
        result.append(clean[cursor:start])
        token = clean[start:end]
        result.append(colorize(token, style, color))
        cursor = end
    result.append(clean[cursor:])
    return "".join(result)


def _infer_annotation_targets(message: str) -> int:
    clean = message.replace("`", "")
    for pattern in _ANNOTATION_ARG_PATTERNS:
        match = pattern.search(clean)
        if not match:
            continue
        raw = match.group(1)
        candidates = [token.strip(" ,.:;'\"") for token in raw.split(",")]
        names = [name for name in candidates if name]
        if names:
            return len(names)
    return 0


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
        code_display = f" [{code_value}]" if code_value else ""
        padded_location = location.ljust(location_width) if location_width else location
        padding = " " if padded_location else ""
        message = _clean_message(code_value, diag.message)
        location_display = _highlight_for_output(padded_location, color=cfg.color)
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
        label: sum(metric.suppressions.get(label, 0) for metric in metrics.values())
        for label in SUPPRESSION_LABELS
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

    diagnostics = [
        {
            "file": item[0],
            "line": item[1] if item[1] >= 0 else None,
            "function": item[2],
            "tool": (item[3] or "").lower(),
            "code": ("" if item[4] == "-" else item[4]).upper(),
            "message": item[5],
        }
        for item in entries
    ]

    advice_messages: list[str] = []
    seen: set[str] = set()

    def add_advice(message: str) -> None:
        if message in seen:
            return
        seen.add(message)
        advice_messages.append(message)

    def is_test_path(path: str | None) -> bool:
        if not path:
            return False
        normalized = path.replace("\\", "/")
        segments = normalized.split("/")
        return any(segment.startswith("test") or segment == "tests" for segment in segments)

    # Complexity hotspots
    complexity_codes = {
        ("pylint", "R1260"),
        ("pylint", "R0915"),
        ("ruff", "C901"),
        ("ruff", "PLR0915"),
    }
    complexity_targets: dict[tuple[str, str], tuple[str, str]] = {}
    for record in diagnostics:
        key = (record["tool"], record["code"])
        if key not in complexity_codes:
            continue
        file_path = record["file"] or "this module"
        function = record["function"] or ""
        complexity_targets[(file_path, function)] = (file_path, function)

    if complexity_targets:
        function_targets: list[tuple[str, str]] = []
        file_only_targets: list[str] = []
        for file_path, function in complexity_targets.values():
            if function:
                function_targets.append((file_path, function))
            elif file_path:
                file_only_targets.append(file_path)

        if function_targets:
            hot_spots: list[tuple[str, str, int | None, int | None]] = []
            for file_path, function in function_targets:
                size, complexity = _estimate_function_scale(Path(file_path), function)
                hot_spots.append((file_path, function, size, complexity))

            def sort_key(item: tuple[str, str, int | None, int | None]) -> tuple[int, int, str]:
                locs = item[2] if isinstance(item[2], int) else -1
                compl = item[3] if isinstance(item[3], int) else -1
                return (-locs, -compl, f"{item[0]}::{item[1]}")

            top_spots = sorted(hot_spots, key=sort_key)[:5]
            if top_spots:
                summary_bits = []
                for file_path, function, size, complexity in top_spots:
                    descriptor = f"function {function} in {file_path}"
                    details: list[str] = []
                    if isinstance(size, int) and size >= 0:
                        details.append(f"~{size} lines")
                    if isinstance(complexity, int) and complexity >= 0:
                        details.append(f"complexity≈{complexity}")
                    if details:
                        descriptor = f"{descriptor} ({', '.join(details)})"
                    summary_bits.append(descriptor)
                add_advice(
                    "Refactor priority: focus on "
                    + "; ".join(summary_bits)
                    + " to restore single-responsibility boundaries before tuning the rest.",
                )

        if file_only_targets:
            summary = _summarise_paths(sorted(set(file_only_targets)))
            if summary:
                add_advice(
                    f"Refactor: break {summary} into smaller pieces to uphold Single Responsibility and keep cyclomatic complexity in check.",
                )

    # Documentation gaps
    doc_counts: defaultdict[str, int] = defaultdict(int)
    for record in diagnostics:
        code = record["code"]
        if not code:
            continue
        if (
            record["tool"] == "ruff" and (code.startswith("D1") or code in {"D401", "D402"})
        ) or code in {"TC002", "TC003"}:
            doc_counts[record["file"]] += 1
    doc_targets = [
        file_path
        for file_path, count in sorted(doc_counts.items(), key=lambda item: item[1], reverse=True)
        if count >= 3 and file_path
    ]
    if doc_targets:
        summary = _summarise_paths(doc_targets)
        if summary:
            add_advice(
                "Documentation: add module/function docstrings in "
                f"{summary} so collaborators can follow intent without reading every branch—Google-style docstrings are recommended for clarity and consistency.",
            )

    # Type-annotation hygiene
    type_counts: defaultdict[str, int] = defaultdict(int)
    annotation_keywords = {"annotation", "typed", "type hint"}
    for record in diagnostics:
        code = record["code"]
        msg_lower = record["message"].lower()
        file_path = record["file"]
        if not file_path:
            continue
        if record["tool"] == "ruff" and code.startswith("ANN"):
            multiplier = _infer_annotation_targets(record["message"])
            type_counts[file_path] += multiplier if multiplier > 0 else 1
        elif record["tool"] in {"mypy", "pyright"}:
            if (
                code.startswith("ARG")
                or code.startswith("VAR")
                or any(keyword in msg_lower for keyword in annotation_keywords)
            ):
                multiplier = _infer_annotation_targets(record["message"])
                type_counts[file_path] += multiplier if multiplier > 0 else 1
    type_targets = [
        file_path
        for file_path, count in sorted(type_counts.items(), key=lambda item: item[1], reverse=True)
        if count >= 3
    ]
    if type_targets:
        summary = _summarise_paths(type_targets)
        if summary:
            add_advice(
                f"Types: introduce explicit annotations in {summary} to narrow interfaces and align with Interface Segregation.",
            )

    # Stub maintenance issues
    stub_flags = {
        record["file"]
        for record in diagnostics
        if (record["file"] or "").endswith(".pyi")
        and record["tool"] == "ruff"
        and record["code"].startswith("ANN")
    }
    override_flags = {
        record["file"]
        for record in diagnostics
        if record["tool"] == "pyright"
        and (
            "override" in record["message"].lower()
            or record["code"].startswith("REPORTINCOMPATIBLE")
            or record["code"] == "REPORTMETHODOVERRIDESIGNATURE"
        )
    }
    if stub_flags and override_flags:
        add_advice(
            "Typing: align stubs with implementations—double-check stub signatures against code and update when upstream changes land.",
        )

    # Implicit namespace packages
    for record in diagnostics:
        if record["code"] == "INP001":
            target = record["file"] or record["message"].split()[0]
            directory = str(Path(target).parent) if target else "this package"
            location = directory or "."
            add_advice(
                f"Packaging: add an __init__.py to {location} so imports stay predictable and tooling can locate modules.",
            )
            break

    # Private/internal imports
    private_codes = {"SLF001", "TID252"}
    private_keywords = {"private import", "module is internal"}
    for record in diagnostics:
        code = record["code"]
        message = record["message"].lower()
        if code in private_codes:
            add_advice(
                "Encapsulation: expose public APIs instead of importing internal members; re-export what callers need.",
            )
            break
        if record["tool"] == "pyright" and (
            code == "REPORTPRIVATEIMPORTUSAGE"
            or any(keyword in message for keyword in private_keywords)
        ):
            add_advice(
                "Encapsulation: expose public APIs instead of importing internal members; re-export what callers need.",
            )
            break

    # Magic values
    magic_counts: defaultdict[str, int] = defaultdict(int)
    for record in diagnostics:
        if record["code"] == "PLR2004" and record["file"]:
            magic_counts[record["file"]] += 1
    magic_targets = [
        file_path
        for file_path, count in sorted(magic_counts.items(), key=lambda item: item[1], reverse=True)
        if count >= 2
    ]
    if magic_targets:
        summary = _summarise_paths(magic_targets)
        if summary:
            add_advice(
                f"Constants: move magic numbers in {summary} into named constants or configuration objects for clarity.",
            )

    # Debug artifacts
    debug_codes = {"T201", "ERA001"}
    if any(record["code"] in debug_codes for record in diagnostics):
        add_advice(
            "Logging: replace debugging prints or commented blocks with structured logging or tests before merging.",
        )

    # Production assertions
    for record in diagnostics:
        if record["code"] in {"S101", "B101"} and not is_test_path(record["file"]):
            add_advice(
                "Runtime safety: swap bare assert with explicit condition checks or exceptions so optimized builds keep validation.",
            )
            break

    # Test hygiene
    test_diagnostics = [record for record in diagnostics if is_test_path(record["file"])]
    if len(test_diagnostics) >= 5:
        add_advice(
            "Test hygiene: refactor noisy tests to shared helpers or fixtures and split long assertions so failures isolate quickly.",
        )

    # Duplicate code
    duplicate_hit = False
    for record in diagnostics:
        tool_codes = _DUPLICATE_HINT_CODES.get(record["tool"], set())
        if record["code"] in tool_codes:
            duplicate_hit = True
            break
    if duplicate_hit:
        add_advice(
            "Structure: deduplicate repeated logic or declarations—extract helpers or consolidate definitions to stay Open/Closed and reduce drift.",
        )

    # Undef interfaces / attribute access across modules
    for record in diagnostics:
        if record["tool"] in {"pyright", "mypy"} and record["code"] in {
            "REPORTUNDEFINEDVARIABLE",
            "ATTR-DEFINED",
            "ATTRDEFINED",
        }:
            file_path = record["file"] or "this module"
            add_advice(
                f"Interface: reconcile module boundaries in {file_path} by defining the missing attribute or exporting it explicitly.",
            )
            break

    # Focus suggestion for highest density file
    file_counter = Counter(record["file"] for record in diagnostics if record["file"])
    if file_counter:
        file_path, count = file_counter.most_common(1)[0]
        if count >= 8:
            add_advice(
                f"Prioritise: focus on {file_path} first; it triggered {count} diagnostics in this run.",
            )

    if not advice_messages:
        return

    console = console_manager.get(color=cfg.color, emoji=cfg.emoji)

    def stylise(line: str) -> Text:
        if not cfg.color:
            return Text(line)
        parts = line.split(": ", 1)
        if len(parts) == 2:
            label, rest = parts
            prefix = Text(f"{label}: ", style="bold yellow")
            rest_text = _apply_highlighting_text(rest)
            return prefix + rest_text
        return _apply_highlighting_text(line)

    panel = Panel(
        Text("\n").join(stylise(message) for message in advice_messages),
        title="SOLID Advice",
        border_style="cyan" if cfg.color else "none",
    )
    console.print(panel)
