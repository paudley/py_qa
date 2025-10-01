# SPDX-License-Identifier: MIT
"""Render SOLID advice guidance for concise output."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from rich.panel import Panel
from rich.text import Text

from ..annotations import AnnotationEngine
from ..config import OutputConfig
from ..console import console_manager
from .advice import AdviceEntry, generate_advice


def _sentence_case(text: str) -> str:
    """Return *text* with the leading alphabetical character lower-cased.

    Args:
        text: Source text to normalise.

    Returns:
        str: Sentence-cased text when possible.
    """

    if not text:
        return text
    first = text[0]
    if first.isalpha():
        return f"{first.lower()}{text[1:]}"
    return text


def render_advice_panel(
    entries: Iterable[tuple[str, int, str, str, str, str]],
    cfg: OutputConfig,
    *,
    annotation_engine: AnnotationEngine,
    highlight: Callable[[str], Text],
) -> None:
    """Render SOLID advice guidance when entries are available.

    Args:
        entries: Normalised diagnostics used for advice generation.
        cfg: Output configuration describing formatting preferences.
        annotation_engine: Annotation engine used for advice generation.
        highlight: Callable that converts diagnostic text into Rich markup.
    """

    normalized_entries = list(entries)
    if not normalized_entries:
        return

    advice_entries = generate_advice(normalized_entries, annotation_engine)
    if not advice_entries:
        return

    console = console_manager.get(color=cfg.color, emoji=cfg.emoji)

    def stylise(entry: AdviceEntry) -> Text:
        """Return a Rich text representation of an advice entry."""

        body_text = _sentence_case(entry.body)
        if not cfg.color:
            return Text(f"{entry.category}: {body_text}")
        prefix = Text(f"{entry.category}: ", style="bold yellow")
        rest_text = highlight(body_text)
        return prefix + rest_text

    body = Text()
    body.no_wrap = False
    for idx, entry in enumerate(advice_entries):
        line = stylise(entry)
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


__all__ = ["render_advice_panel"]
