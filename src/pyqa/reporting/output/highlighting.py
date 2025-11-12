# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Rich text highlighting utilities shared across reporting renderers."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Final

from rich.style import Style
from rich.text import Text

from ...analysis.providers import NullAnnotationProvider
from ...core.models import RunResult
from ...interfaces.analysis import (
    AnnotationProvider,
    DiagnosticAnnotation,
    MessageSpan,
    SimpleMessageSpan,
)


class _AnnotationRouter(AnnotationProvider):
    """Route annotation calls to the currently active provider."""

    def __init__(self, provider: AnnotationProvider) -> None:
        """Initialise the router with ``provider`` as the active delegate.

        Args:
            provider: Default provider that will receive annotation calls until
                :meth:`replace` is invoked.
        """

        self._provider = provider

    def replace(self, provider: AnnotationProvider) -> None:
        """Update the underlying provider used for annotation calls.

        Args:
            provider: New provider that should service annotation requests.
        """

        self._provider = provider

    def annotate_run(self, result: RunResult) -> dict[int, DiagnosticAnnotation]:
        """Delegate run annotation to the active provider.

        Args:
            result: Run result whose diagnostics require annotation.

        Returns:
            Mapping of diagnostic ids to annotation metadata.
        """

        return dict(self._provider.annotate_run(result))

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


def _coerce_span(span: MessageSpan) -> SimpleMessageSpan:
    """Return a ``SimpleMessageSpan`` mirroring ``span`` values.

    Args:
        span: Span emitted by an annotation provider.

    Returns:
        SimpleMessageSpan: Span with guaranteed ``style`` and ``kind`` attributes.
    """

    style = getattr(span, "style", ANNOTATION_SPAN_STYLE)
    kind = getattr(span, "kind", None)
    return SimpleMessageSpan(start=span.start, end=span.end, style=str(style), kind=kind)


def _coerce_spans(spans: Sequence[MessageSpan]) -> list[SimpleMessageSpan]:
    """Return ``spans`` converted into ``SimpleMessageSpan`` instances.

    Args:
        spans: Sequence of spans that may not expose ``SimpleMessageSpan`` fields.

    Returns:
        list[SimpleMessageSpan]: Converted span sequence.
    """

    return [_coerce_span(span) for span in spans]


def collect_highlight_spans(
    text: str,
    *,
    engine: AnnotationProvider | None = None,
) -> list[SimpleMessageSpan]:
    """Return annotation spans present in *text* using the provided engine.

    Args:
        text: Diagnostic message text to analyse.
        engine: Optional provider overriding the module-level annotation engine.

    Returns:
        list[SimpleMessageSpan]: Normalised spans annotated with style metadata.
    """

    target_engine = engine or _ANNOTATION_ROUTER
    spans: list[SimpleMessageSpan] = []
    for span in target_engine.message_spans(text):
        spans.append(_coerce_span(span))
    return spans


def strip_literal_quotes(text: str) -> tuple[str, list[SimpleMessageSpan]]:
    """Return text with ``''literal''`` markers removed while tracking spans.

    Args:
        text: Message text that may contain double-quoted literal markers.

    Returns:
        tuple[str, list[SimpleMessageSpan]]: Cleaned text paired with literal
        spans suitable for downstream highlighting.
    """

    segments: list[str] = []
    spans: list[SimpleMessageSpan] = []
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
    """Return a Rich text object with annotation-aware highlighting applied.

    Args:
        message: Diagnostic message subject to highlighting.
        base_style: Optional Rich style applied to the entire message.
        engine: Optional annotation provider overriding the module default.

    Returns:
        Text: Rich text object carrying the highlighted message content.
    """

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
) -> list[SimpleMessageSpan]:
    """Return highlight spans for function suffixes in location strings.

    Args:
        location: Fully qualified diagnostic location string.
        separator: Delimiter used between file path and symbol location.

    Returns:
        list[SimpleMessageSpan]: Spans highlighting the trailing function name
        when present; otherwise an empty list.
    """

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
    """Return Rich text with inline highlighting suitable for terminal output.

    Args:
        message: Text to highlight for console output.
        color: Flag indicating whether colour highlighting is enabled.
        extra_spans: Additional spans that should be highlighted.
        engine: Optional provider overriding the module-level annotation engine.

    Returns:
        Text: Highlighted message (or plain text when colouring disabled).
    """

    clean = message.replace("`", "")
    if not color:
        clean, _ = strip_literal_quotes(clean)
        return Text(clean)
    clean, literal_spans = strip_literal_quotes(clean)
    spans = collect_highlight_spans(clean, engine=engine)
    spans.extend(literal_spans)
    if extra_spans:
        spans.extend(_coerce_spans(extra_spans))
    text = Text(clean)
    spans.sort(key=lambda span: (span.start, span.end))
    for span in spans:
        style = _style_from_code(span.style)
        if style is None:
            continue
        text.stylize(style, span.start, span.end)
    return text


def format_code_value(code: str, color_enabled: bool) -> Text:
    """Return a colourised diagnostic code for concise output.

    Args:
        code: Diagnostic code string.
        color_enabled: Flag indicating whether colour styling should apply.

    Returns:
        Text: Rich text object containing the diagnostic code.
    """

    clean = code.strip() or EMPTY_CODE_PLACEHOLDER
    text = Text(clean)
    if not color_enabled or clean == EMPTY_CODE_PLACEHOLDER:
        return text
    style = _style_from_code(CODE_TINT)
    if style is not None:
        text.stylize(style)
    return text


def _style_from_code(style_code: str | None) -> Style | None:
    """Return a Rich style constructed from ``style_code`` tokens.

    Args:
        style_code: Style token describing colour information.

    Returns:
        Style | None: Rich style when recognised; otherwise ``None``.
    """

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
