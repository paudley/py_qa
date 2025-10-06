# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Console formatters for orchestrator results."""

from __future__ import annotations

import re
from collections import OrderedDict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from ...config import OutputConfig
from ...filesystem.paths import normalize_path
from ...logging import colorize, emoji
from ...models import Diagnostic, RunResult
from ..advice.panels import render_advice_panel
from ..advice.refactor import render_refactor_navigator
from ..output.diagnostics import (
    MISSING_CODE_PLACEHOLDER,
    clean_message,
)
from ..output.highlighting import (
    ANNOTATION_ENGINE,
    ANNOTATION_SPAN_STYLE,
    LOCATION_SEPARATOR,
    apply_highlighting_text,
    format_code_value,
    highlight_for_output,
    location_function_spans,
)
from ..output.modes import (
    render_pretty_mode,
    render_quiet_mode,
    render_raw_mode,
)
from .stats import emit_stats_panel

CONCISE_MISSING_LINE: Final[int] = -1
CONCISE_MISSING_CODE: Final[str] = MISSING_CODE_PLACEHOLDER
TOOL_PADDING_LIMIT: Final[int] = 10
MAX_SYMBOL_LENGTH: Final[int] = 80
ELLIPSIS: Final[str] = "…"
ELLIPSIS_CUTOFF: Final[int] = MAX_SYMBOL_LENGTH - len(ELLIPSIS)
ALLOWED_SYMBOL_CHARS: Final[frozenset[str]] = frozenset(
    {"_", ".", "-", ":", "<", ">", "[", "]", "(", ")"},
)
SYMBOL_COMMENT_PREFIXES: Final[tuple[str, ...]] = ("#", '"""', "'''")
DEFAULT_CONCISE_MESSAGE: Final[str] = "<no message provided>"
DUPLICATE_CODE_TAG: Final[str] = "duplicate-code"


@dataclass(slots=True)
class ConciseDiagnostic:
    """Structured representation of concise formatter output."""

    file_path: str
    line: int | None
    function: str
    tool: str
    code: str
    message: str

    def as_advice_tuple(self) -> tuple[str, int, str, str, str, str]:
        """Return a tuple compatible with advice generation.

        Returns:
            tuple[str, int, str, str, str, str]: Advice builder tuple describing
            the diagnostic.
        """

        return (
            self.file_path,
            self.line if self.line is not None else CONCISE_MISSING_LINE,
            self.function,
            self.tool,
            self.code or CONCISE_MISSING_CODE,
            self.message,
        )

    def location_suffix(self) -> str:
        """Return the location suffix including line and function.

        Returns:
            str: Location suffix formatted as ``:line[:function]`` when
            applicable.
        """

        parts: list[str] = []
        if self.line is not None and self.line >= 0:
            parts.append(str(self.line))
        if self.function:
            parts.append(self.function)
        return f"{LOCATION_SEPARATOR}{LOCATION_SEPARATOR.join(parts)}" if parts else ""

    def with_message(self, message: str) -> ConciseDiagnostic:
        """Return a copy of the diagnostic with an updated message.

        Args:
            message: Replacement message for the diagnostic.

        Returns:
            ConciseDiagnostic: New diagnostic containing *message*.
        """

        return ConciseDiagnostic(
            file_path=self.file_path,
            line=self.line,
            function=self.function,
            tool=self.tool,
            code=self.code,
            message=message,
        )


_MERGEABLE_MESSAGE = re.compile(r"^(?P<prefix>.*?)(`(?P<detail>[^`]+)`)(?P<suffix>.*)$")


def render(result: RunResult, cfg: OutputConfig) -> None:
    """Render orchestrator results according to the configured output style.

    Args:
        result: Completed orchestrator run result to display.
        cfg: Output configuration describing formatting preferences.
    """

    ANNOTATION_ENGINE.annotate_run(result)
    if cfg.quiet:
        render_quiet_mode(result, cfg)
        return
    match cfg.output:
        case "pretty":
            render_pretty_mode(result, cfg)
            emit_stats_panel(
                result,
                cfg,
                sum(len(outcome.diagnostics) for outcome in result.outcomes),
            )
        case "raw":
            render_raw_mode(result)
        case "concise" | _:
            _render_concise(result, cfg)


def _render_concise(result: RunResult, cfg: OutputConfig) -> None:
    """Render a concise, machine-friendly summary of diagnostics.

    Args:
        result: Completed orchestrator run result to display.
        cfg: Output configuration describing formatting preferences.
    """

    root_path = _resolve_root_path(result.root)
    total_actions = len(result.outcomes)
    failed_actions = sum(1 for outcome in result.outcomes if outcome.indicates_failure())

    raw_entries = _collect_concise_entries(result, root_path)
    entries = _group_similar_entries(raw_entries)
    _print_concise_entries(entries, result, cfg)

    diagnostics_count = len(entries)
    if getattr(cfg, "advice", False):
        advice_input = [entry.as_advice_tuple() for entry in entries]
        render_advice_panel(
            advice_input,
            cfg,
            annotation_engine=ANNOTATION_ENGINE,
            highlight=apply_highlighting_text,
        )
        render_refactor_navigator(result, cfg)
    emit_stats_panel(result, cfg, diagnostics_count)
    _render_concise_summary(result, cfg, total_actions, failed_actions, diagnostics_count)


def _render_concise_summary(
    result: RunResult,
    cfg: OutputConfig,
    total_actions: int,
    failed_actions: int,
    diagnostics_count: int,
) -> None:
    """Print the concise summary footer with overall status.

    Args:
        result: Completed orchestrator run result to summarise.
        cfg: Output configuration describing formatting preferences.
        total_actions: Total actions executed in the run.
        failed_actions: Count of actions that failed.
        diagnostics_count: Number of concise diagnostics emitted.
    """

    files_count = len(result.files)
    cached_actions = sum(1 for outcome in result.outcomes if outcome.cached)

    label_text = "Failed" if failed_actions else "Passed"
    summary_symbol = emoji("❌" if failed_actions else "✅", cfg.emoji)
    summary_label = f"{summary_symbol} {label_text}" if summary_symbol else label_text
    summary_color = "red" if failed_actions else "green"

    stats_parts = [
        f"{diagnostics_count} diagnostic(s) across {files_count} file(s)",
        f"{failed_actions} failing action(s) out of {total_actions}",
    ]
    if cached_actions:
        stats_parts.append(f"{cached_actions} cached action(s)")

    stats_body = "— " + "; ".join(stats_parts)
    status_text = colorize(summary_label, summary_color, cfg.color)
    stats_text = colorize(stats_body, "white", cfg.color)
    print(f"{status_text} {stats_text}".strip())


def _resolve_root_path(raw_root: str | Path) -> Path:
    """Return the project root used for concise rendering.

    Args:
        raw_root: Raw root path provided by the run result.

    Returns:
        Path: Resolved root path when accessible, otherwise the original path.
    """

    root_path = Path(raw_root)
    try:
        return root_path.resolve()
    except OSError:
        return root_path


def _normalize_concise_path(path_str: str | None, root: Path) -> str:
    """Return the diagnostic path normalised relative to *root*."""

    if not path_str:
        return "<unknown>"
    try:
        normalised = normalize_path(path_str, base_dir=root)
    except (ValueError, OSError):
        return str(path_str)
    return normalised.as_posix()


def _build_concise_entry(
    diagnostic: Diagnostic,
    fallback_tool: str,
    root_path: Path,
) -> ConciseDiagnostic:
    """Construct a concise diagnostic entry from a raw diagnostic record.

    Args:
        diagnostic: Diagnostic emitted by a tool.
        fallback_tool: Tool name to use when the diagnostic lacks one.
        root_path: Resolved project root used for relative path rendering.

    Returns:
        ConciseDiagnostic: Normalised diagnostic ready for concise output.
    """

    tool_name = diagnostic.tool or fallback_tool
    file_path = _normalize_concise_path(diagnostic.file, root_path)
    line_no = diagnostic.line
    code_value = (diagnostic.code or CONCISE_MISSING_CODE).strip() or CONCISE_MISSING_CODE
    first_line = diagnostic.message.splitlines()[0] if diagnostic.message else ""
    if (diagnostic.code or "").strip().lower() == DUPLICATE_CODE_TAG:
        summary = _summarize_duplicate_code(diagnostic.message, root_path)
        if summary:
            first_line = summary
    message = clean_message(code_value, first_line) or DEFAULT_CONCISE_MESSAGE
    function = _normalise_symbol(diagnostic.function)
    return ConciseDiagnostic(
        file_path=file_path,
        line=line_no,
        function=function,
        tool=tool_name,
        code=code_value,
        message=message,
    )


def _collect_concise_entries(result: RunResult, root_path: Path) -> list[ConciseDiagnostic]:
    """Collect deduplicated concise diagnostics from a run result.

    Args:
        result: Completed orchestrator run result containing diagnostics.
        root_path: Resolved project root used for relative paths.

    Returns:
        list[ConciseDiagnostic]: Unique concise diagnostics for rendering.
    """

    seen: set[tuple[str, int, str, str, str, str]] = set()
    entries: list[ConciseDiagnostic] = []

    for outcome in result.outcomes:
        for diag in outcome.diagnostics:
            entry = _build_concise_entry(diag, outcome.tool, root_path)
            record_key = entry.as_advice_tuple()
            if record_key in seen:
                continue
            seen.add(record_key)
            entries.append(entry)

    return entries


def _group_similar_entries(entries: list[ConciseDiagnostic]) -> list[ConciseDiagnostic]:
    """Merge diagnostics that differ only by backtick-delimited details.

    Args:
        entries: Concise diagnostics to group by shared context.

    Returns:
        list[ConciseDiagnostic]: Diagnostics with merged inline details.
    """

    if not entries:
        return []

    grouped: OrderedDict[
        tuple[str, int | None, str, str, str, str, str],
        _GroupBucket,
    ] = OrderedDict()

    for entry in entries:
        prefix, detail, suffix = _split_mergeable_message(entry.message)
        key = (entry.file_path, entry.line, entry.function, entry.tool, entry.code, prefix, suffix)
        bucket = grouped.get(key)
        if bucket is None:
            initial_message = entry.message if not detail else f"{prefix}{detail}{suffix}".strip()
            bucket = _GroupBucket(
                entry=entry.with_message(initial_message.replace("`", "")),
                prefix=prefix,
                suffix=suffix,
                details=[],
            )
            grouped[key] = bucket
        if detail:
            normalized_detail = detail.replace("`", "")
            if normalized_detail not in bucket.details:
                bucket.details.append(normalized_detail)

    merged: list[ConciseDiagnostic] = []
    for bucket in grouped.values():
        if not bucket.details:
            merged.append(bucket.entry)
            continue
        if len(bucket.details) == 1:
            message = f"{bucket.prefix}{bucket.details[0]}{bucket.suffix}".strip()
        else:
            combined = ", ".join(bucket.details)
            message = f"{bucket.prefix}{combined}{bucket.suffix}".strip()
        merged.append(bucket.entry.with_message(message.replace("`", "")))
    return merged


def _split_mergeable_message(message: str) -> tuple[str, str, str]:
    """Split a message into prefix, mergeable detail, and suffix fragments.

    Args:
        message: Diagnostic message potentially containing `` `detail` ``.

    Returns:
        tuple[str, str, str]: Prefix, detail, and suffix components.
    """
    match = _MERGEABLE_MESSAGE.match(message)
    if not match:
        sanitized = message.replace("`", "")
        return sanitized, "", ""
    prefix = match.group("prefix") or ""
    detail = match.group("detail") or ""
    suffix = match.group("suffix") or ""
    return prefix.replace("`", ""), detail.replace("`", ""), suffix.replace("`", "")


@dataclass(slots=True)
class _GroupBucket:
    """Intermediate container for grouping similar messages."""

    entry: ConciseDiagnostic
    prefix: str
    suffix: str
    details: list[str]


def _print_concise_entries(
    entries: Sequence[ConciseDiagnostic],
    result: RunResult,
    cfg: OutputConfig,
) -> None:
    """Emit concise diagnostics to stdout.

    Args:
        entries: Concise diagnostics ready for printing.
        result: Completed run result containing additional metadata.
        cfg: Output configuration describing formatting preferences.
    """

    if not entries:
        return

    tool_width = 0
    tool_names = [entry.tool for entry in entries]
    if tool_names:
        raw_tool_width = max(len(tool) for tool in tool_names)
        tool_width = min(raw_tool_width, TOOL_PADDING_LIMIT)

    tint_tool = _tool_tinter(result, cfg)
    for entry in sorted(
        entries,
        key=lambda item: (
            item.file_path,
            item.line if item.line is not None else float("inf"),
            item.function,
            item.tool,
            item.code,
            item.message,
        ),
    ):
        spacer = " " * max(tool_width - len(entry.tool), 0) if tool_width else ""
        location = (entry.file_path or "") + entry.location_suffix()
        location_display = highlight_for_output(
            location,
            color=cfg.color,
            extra_spans=location_function_spans(location),
        )
        message_display = highlight_for_output(entry.message, color=cfg.color)
        code_display = format_code_value(entry.code, cfg.color)
        tool_display = tint_tool(entry.tool)
        print(
            f"{tool_display}, {spacer}{location_display}, {code_display}, {message_display}",
        )


def _tool_tinter(result: RunResult, cfg: OutputConfig) -> Callable[[str], str]:
    """Return a function that colourises tool names when colour is enabled.

    Args:
        result: Completed run result providing the list of tools.
        cfg: Output configuration describing formatting preferences.

    Returns:
        Callable[[str], str]: Function that colourises tool names for output.
    """
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
    """Return a compact symbol name for concise output.

    Args:
        value: Raw function or symbol name extracted from diagnostics.

    Returns:
        str: Sanitised symbol suitable for concise output, or an empty string
        when the value is unsuitable.
    """

    if not value:
        return ""
    candidate = value.strip()
    if not candidate:
        return ""
    sanitized = candidate.splitlines()[0].strip()
    if not sanitized:
        return ""

    invalid = (
        sanitized.startswith(SYMBOL_COMMENT_PREFIXES)
        or any(char.isspace() for char in sanitized)
        or any(not ch.isalnum() and ch not in ALLOWED_SYMBOL_CHARS for ch in sanitized)
    )
    if invalid:
        return ""

    if len(sanitized) > MAX_SYMBOL_LENGTH:
        sanitized = f"{sanitized[:ELLIPSIS_CUTOFF]}{ELLIPSIS}"
    return sanitized


def _summarize_duplicate_code(message: str, root: Path) -> str:
    """Create a concise duplicate-code message including file references.

    Args:
        message: Raw duplicate-code message from pylint.
        root: Project root used for relative path conversion.

    Returns:
        str: Condensed duplicate-code summary with relative locations.
    """
    lines = [line.strip() for line in message.splitlines() if line.strip()]
    if not lines:
        return ""

    header = lines[0]
    locations: list[str] = []
    for detail in lines[1:]:
        if not detail.startswith("=="):
            continue
        entry = detail[2:]
        name, _, span = entry.partition(":")
        name = name.strip()
        span = span.strip("[] ")
        display = _resolve_duplicate_code_target(name, root)
        if span:
            display = f"{display}:{span}"
        locations.append(display)

    if locations:
        return f"{header}: {', '.join(locations)}"
    return header


def _resolve_duplicate_code_target(name: str, root: Path) -> str:
    """Resolve a pylint duplicate-code location entry to a displayable path.

    Args:
        name: Original target string emitted by pylint.
        root: Project root used for relative path conversion.

    Returns:
        str: Display-friendly path for the duplicate-code entry.
    """
    normalized = name.strip()
    if not normalized:
        return name

    candidate = Path(normalized)
    if candidate.is_absolute():
        return _relative_path_if_possible(candidate, root)

    if candidate.exists():
        return _relative_path_if_possible(candidate, root)

    dotted = normalized.replace("\\", "/").replace(".", "/")
    for suffix in (".py", ".pyi"):
        possible = root / f"{dotted}{suffix}"
        if possible.exists():
            return _relative_path_if_possible(possible, root)

    return normalized


def _relative_path_if_possible(path: Path, root: Path) -> str:
    """Return the path relative to *root* when feasible.

    Args:
        path: Filesystem path to normalise.
        root: Project root used for relative path calculation.

    Returns:
        str: Relative path when possible, otherwise the original path string.
    """

    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _infer_annotation_targets(message: str) -> int:
    """Return the count of highlighted annotation spans within *message*.

    Args:
        message: Diagnostic message to inspect for annotation spans.

    Returns:
        int: Number of annotation spans that match the configured style.
    """

    spans = ANNOTATION_ENGINE.message_spans(message)
    return sum(1 for span in spans if span.style == ANNOTATION_SPAN_STYLE)
