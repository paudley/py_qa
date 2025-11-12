# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""spaCy-powered helpers that derive message spans and signatures."""

from __future__ import annotations

from collections.abc import Callable
from typing import Final, TypeVar

from pyqa.interfaces.analysis import MessageSpan

from .loader import DocLike

DEFAULT_CLASS_STYLE: Final[str] = "ansi256:154"
DEFAULT_VARIABLE_STYLE: Final[str] = "ansi256:208"

SpanT = TypeVar("SpanT", bound=MessageSpan)


def build_spacy_spans(
    doc: DocLike,
    span_factory: Callable[[int, int, str, str | None], SpanT],
) -> list[SpanT]:
    """Identify highlight spans derived from spaCy document tokens.

    Args:
        doc: Tokenised spaCy document representing the diagnostic message.
        span_factory: Callable that constructs ``MessageSpan`` instances.

    Returns:
        list[MessageSpan]: Highlight spans identified by analysing the document.
    """

    spans: list[SpanT] = []
    for token in doc:
        if token.is_stop or not token.text.strip():
            continue
        if token.text[0].isupper() and token.text.isalpha():
            spans.append(
                span_factory(
                    token.idx,
                    token.idx + len(token.text),
                    DEFAULT_CLASS_STYLE,
                    "class",
                ),
            )
        if token.pos_ in {"PROPN", "NOUN"} and token.text.isidentifier():
            spans.append(
                span_factory(
                    token.idx,
                    token.idx + len(token.text),
                    DEFAULT_VARIABLE_STYLE,
                    "variable",
                ),
            )
    return spans


def iter_signature_tokens(doc: DocLike) -> list[str]:
    """Identify semantic signature tokens for the supplied document.

    Args:
        doc: Tokenised spaCy document representing the diagnostic message.

    Returns:
        list[str]: Ordered list of lemma-based signature tokens.
    """

    tokens: list[str] = []
    for token in doc:
        if token.is_stop or not token.text.strip():
            continue
        if token.pos_ in {"NOUN", "PROPN", "VERB", "ADJ"}:
            lemma = token.lemma_.lower().strip()
            if lemma:
                tokens.append(lemma)
    return tokens


__all__ = [
    "build_spacy_spans",
    "iter_signature_tokens",
]
