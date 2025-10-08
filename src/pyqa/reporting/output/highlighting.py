# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Rich text highlighting utilities shared across reporting renderers."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any, Final

from rich.text import Text

from ...analysis import MessageSpan as AnalysisMessageSpan
from ...analysis.providers import NullAnnotationProvider
from ...core.logging import colorize
from ...interfaces.analysis import AnnotationProvider
from ...interfaces.analysis import MessageSpan as MessageSpanProtocol


class _AnnotationRouter(AnnotationProvider):
    """Route annotation calls to the currently active provider."""

    def __init__(self, provider: AnnotationProvider) -> None:
        self._provider = provider

    def replace(self, provider: AnnotationProvider) -> None:
        """Update the underlying provider used for annotation calls.

        Args:
            provider: New provider that should service annotation requests.
        """

        self._provider = provider

    def annotate_run(self, result: Any) -> dict[int, Any]:
        """Delegate run annotation to the active provider.

        Args:
            result: Run result whose diagnostics require annotation.

        Returns:
            Mapping of diagnostic ids to annotation metadata.
        """

        return self._provider.annotate_run(result)

    def message_spans(self, message: str) -> Sequence[MessageSpanProtocol]:
        """Return spans detected in ``message`` using the active provider.

        Args:
            message: Diagnostic message text to analyse.

        Returns:
            Sequence of message spans emitted by the provider.
        """

        return self._provider.message_spans(message)

    def message_signature(self, message: str) -> Sequence[str]:
        """Return signature tokens extracted from ``message``.

        Args:
            message: Diagnostic message text to analyse.

        Returns:
            Sequence of signature tokens describing key entities.
        """

        return self._provider.message_signature(message)


_ANNOTATION_ROUTER = _AnnotationRouter(NullAnnotationProvider())
ANNOTATION_ENGINE: AnnotationProvider = _ANNOTATION_ROUTER


def set_annotation_provider(provider: AnnotationProvider) -> None:
    """Override the module-level annotation provider used for highlighting.

    Args:
        provider: Provider that should power highlighting operations.
    """

    _ANNOTATION_ROUTER.replace(provider)


CODE_TINT: Final[str] = "ansi256:105"
LITERAL_TINT: Final[str] = "ansi256:208"
ANNOTATION_SPAN_STYLE: Final[str] = "ansi256:213"
LOCATION_SEPARATOR: Final[str] = ":"
EMPTY_CODE_PLACEHOLDER: Final[str] = "-"
_LITERAL_PATTERN = re.compile(r"''(.*?)''")


def collect_highlight_spans(
    text: str,
    *,
    engine: AnnotationProvider | None = None,
) -> list[AnalysisMessageSpan]:
    """Return annotation spans present in *text* using the provided engine."""

    target_engine = engine or _ANNOTATION_ROUTER
    spans: list[AnalysisMessageSpan] = []
    for span in target_engine.message_spans(text):
        spans.append(
            AnalysisMessageSpan(
                start=span.start,
                end=span.end,
                style=getattr(span, "style", ""),
                kind=getattr(span, "kind", None),
            ),
        )
    return spans


def strip_literal_quotes(text: str) -> tuple[str, list[AnalysisMessageSpan]]:
    """Return text with ``''literal''`` markers removed while tracking spans."""

    segments: list[str] = []
    spans: list[AnalysisMessageSpan] = []
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
                AnalysisMessageSpan(
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
    engine: AnnotationProvider | None = None,
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
) -> list[AnalysisMessageSpan]:
    """Return highlight spans for function suffixes in location strings."""

    if separator not in location:
        return []
    candidate = location.split(separator)[-1].strip()
    if not candidate or not candidate.isidentifier():
        return []
    start = location.rfind(candidate)
    if start == -1:
        return []
    return [AnalysisMessageSpan(start=start, end=start + len(candidate), style="ansi256:208")]


def highlight_for_output(
    message: str,
    *,
    color: bool,
    extra_spans: Sequence[AnalysisMessageSpan] | None = None,
    engine: AnnotationProvider | None = None,
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
    merged: list[AnalysisMessageSpan] = []
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

    clean = code.strip() or EMPTY_CODE_PLACEHOLDER
    if clean == EMPTY_CODE_PLACEHOLDER:
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
    "set_annotation_provider",
    "strip_literal_quotes",
]
