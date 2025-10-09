# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Rich text highlighting utilities shared across reporting renderers."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any, Final

from rich.style import Style
from rich.text import Text

from ...analysis.providers import NullAnnotationProvider
from ...interfaces.analysis import AnnotationProvider, MessageSpan, SimpleMessageSpan


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

    def message_spans(self, message: str) -> Sequence[MessageSpan]:
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
    spans: list[MessageSpan] = []
    for span in target_engine.message_spans(text):
        spans.append(
            SimpleMessageSpan(
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
                SimpleMessageSpan(
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
        style = _style_from_code(span.style)
        if style is None:
            continue
        text.stylize(style, span.start, span.end)
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
    return [SimpleMessageSpan(start=start, end=start + len(candidate), style="ansi256:208")]


def highlight_for_output(
    message: str,
    *,
    color: bool,
    extra_spans: Sequence[MessageSpan] | None = None,
    engine: AnnotationProvider | None = None,
) -> Text:
    """Return Rich text with inline highlighting suitable for terminal output."""

    clean = message.replace("`", "")
    if not color:
        clean, _ = strip_literal_quotes(clean)
        return Text(clean)
    clean, literal_spans = strip_literal_quotes(clean)
    spans = collect_highlight_spans(clean, engine=engine)
    spans.extend(literal_spans)
    if extra_spans:
        spans.extend(extra_spans)
    text = Text(clean)
    spans.sort(key=lambda span: (span.start, span.end))
    for span in spans:
        style = _style_from_code(span.style)
        if style is None:
            continue
        text.stylize(style, span.start, span.end)
    return text


def format_code_value(code: str, color_enabled: bool) -> Text:
    """Return a colourised diagnostic code for concise output."""

    clean = code.strip() or EMPTY_CODE_PLACEHOLDER
    text = Text(clean)
    if not color_enabled or clean == EMPTY_CODE_PLACEHOLDER:
        return text
    style = _style_from_code(CODE_TINT)
    if style is not None:
        text.stylize(style)
    return text


def _style_from_code(style_code: str | None) -> Style | None:
    """Return a Rich style constructed from ``style_code`` tokens."""

    if not style_code:
        return None
    if style_code.startswith("ansi256:"):
        value = style_code.split(":", 1)[1]
        return Style(color=f"color({value})")
    return Style.parse(style_code)


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
