# SPDX-License-Identifier: MIT
"""Rich text highlighting utilities shared across reporting renderers."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Final

from rich.text import Text

from ..annotations import AnnotationEngine, MessageSpan
from ..logging import colorize

ANNOTATION_ENGINE = AnnotationEngine()
CODE_TINT: Final[str] = "ansi256:105"
LITERAL_TINT: Final[str] = "ansi256:208"
ANNOTATION_SPAN_STYLE: Final[str] = "ansi256:213"
LOCATION_SEPARATOR: Final[str] = ":"
_LITERAL_PATTERN = re.compile(r"''(.*?)''")


def collect_highlight_spans(
    text: str,
    *,
    engine: AnnotationEngine | None = None,
) -> list[MessageSpan]:
    """Return annotation spans present in *text* using the provided engine."""

    target_engine = engine or ANNOTATION_ENGINE
    return list(target_engine.message_spans(text))


def strip_literal_quotes(text: str) -> tuple[str, list[MessageSpan]]:
    """Return text with ``''literal''`` markers removed while tracking spans."""

    segments: list[str] = []
    spans: list[MessageSpan] = []
    cursor = 0
    output_length = 0

    for match in _LITERAL_PATTERN.finditer(text):
        start, end = match.span()
        literal = match.group(1)
        segments.append(text[cursor:start])
        output_length += start - cursor
        segments.append(literal)
        literal_length = len(literal)
        if literal_length:
            spans.append(
                MessageSpan(
                    start=output_length,
                    end=output_length + literal_length,
                    style=LITERAL_TINT,
                ),
            )
        output_length += literal_length
        cursor = end

    segments.append(text[cursor:])
    return "".join(segments), spans


def apply_highlighting_text(
    message: str,
    *,
    base_style: str | None = None,
    engine: AnnotationEngine | None = None,
) -> Text:
    """Return a Rich text object with annotation-aware highlighting applied."""

    clean = message.replace("`", "")
    clean, literal_spans = strip_literal_quotes(clean)
    text = Text(clean)
    if base_style:
        text.stylize(base_style, 0, len(text))
    spans = collect_highlight_spans(clean, engine=engine)
    spans.extend(literal_spans)
    spans.sort(key=lambda span: (span.start, span.end))
    for span in spans:
        text.stylize(span.style, span.start, span.end)
    return text


def location_function_spans(
    location: str,
    *,
    separator: str = LOCATION_SEPARATOR,
) -> list[MessageSpan]:
    """Return highlight spans for function suffixes in location strings."""

    if separator not in location:
        return []
    candidate = location.split(separator)[-1].strip()
    if not candidate or not candidate.isidentifier():
        return []
    start = location.rfind(candidate)
    if start == -1:
        return []
    return [MessageSpan(start=start, end=start + len(candidate), style="ansi256:208")]


def highlight_for_output(
    message: str,
    *,
    color: bool,
    extra_spans: Sequence[MessageSpan] | None = None,
    engine: AnnotationEngine | None = None,
) -> str:
    """Return a string with inline highlighting suitable for terminal output."""

    clean = message.replace("`", "")
    if not color:
        clean, _ = strip_literal_quotes(clean)
        return clean
    clean, literal_spans = strip_literal_quotes(clean)
    spans = collect_highlight_spans(clean, engine=engine)
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


def format_code_value(code: str, color_enabled: bool) -> str:
    """Return a colourised diagnostic code for concise output."""

    clean = code.strip() or "-"
    if clean == "-":
        return clean
    return colorize(clean, CODE_TINT, color_enabled)


__all__ = [
    "ANNOTATION_ENGINE",
    "ANNOTATION_SPAN_STYLE",
    "CODE_TINT",
    "LITERAL_TINT",
    "LOCATION_SEPARATOR",
    "apply_highlighting_text",
    "collect_highlight_spans",
    "format_code_value",
    "highlight_for_output",
    "location_function_spans",
    "strip_literal_quotes",
]
