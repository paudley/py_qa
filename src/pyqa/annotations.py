# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Helpers for enriching diagnostics with Tree-sitter and spaCy hints.

The :class:`AnnotationEngine` resolves structural context via Tree-sitter and
optionally parses diagnostic messages with spaCy (if the language model is
available).  The resulting spans can be reused across renderers to keep
highlighting consistent without re-tokenising every message.
"""

from __future__ import annotations

import os
import re
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

import spacy  # type: ignore[import]
from spacy.cli import download as spacy_download
from spacy.language import Language

from .context import TreeSitterContextResolver
from .models import RunResult


HighlightKind = Literal[
    "file",
    "function",
    "class",
    "argument",
    "variable",
    "attribute",
]


@dataclass(frozen=True)
class MessageSpan:
    """Represents a highlighted segment within a message string."""

    start: int
    end: int
    style: str
    kind: HighlightKind | None = None


@dataclass(frozen=True)
class MessageAnalysis:
    """Cached NLP artefacts for a diagnostic message."""

    spans: tuple[MessageSpan, ...]
    signature: tuple[str, ...]


@dataclass(frozen=True)
class DiagnosticAnnotation:
    """Annotation metadata for a diagnostic."""

    function: str | None
    class_name: str | None
    message_spans: tuple[MessageSpan, ...]


class AnnotationEngine:
    """Annotate diagnostics using Tree-sitter context and spaCy NLP."""

    def __init__(self, model: str | None = None) -> None:
        self._model_name = model or os.getenv("PYQA_NLP_MODEL", "blank:en")
        self._nlp: Language | None = None
        self._nlp_lock = threading.Lock()
        self._resolver = TreeSitterContextResolver()

    def annotate_run(self, result: RunResult) -> dict[int, DiagnosticAnnotation]:
        """Return annotations for each diagnostic in ``result`` keyed by ``id``."""
        annotations: dict[int, DiagnosticAnnotation] = {}
        self._resolver.annotate(
            (diag for outcome in result.outcomes for diag in outcome.diagnostics),
            root=result.root,
        )
        for outcome in result.outcomes:
            for diag in outcome.diagnostics:
                analysis = self._analyse_message(diag.message)
                annotations[id(diag)] = DiagnosticAnnotation(
                    function=diag.function,
                    class_name=None,
                    message_spans=analysis.spans,
                )
        return annotations

    def message_spans(self, message: str) -> tuple[MessageSpan, ...]:
        """Return cached highlight spans for ``message``."""
        return self._analyse_message(message).spans

    def message_signature(self, message: str) -> tuple[str, ...]:
        """Return a semantic signature extracted from ``message``."""
        return self._analyse_message(message).signature

    def language_model(self) -> Language:
        """Return the underlying spaCy language model, loading it if required."""
        return self._get_nlp()

    @lru_cache(maxsize=2048)
    def _analyse_message(self, message: str) -> MessageAnalysis:
        base = message
        spans: list[MessageSpan] = []
        signature_tokens: list[str] = []
        heuristic_spans, heuristic_tokens = _heuristic_spans(base)
        spans.extend(heuristic_spans)
        signature_tokens.extend(heuristic_tokens)
        nlp = self._get_nlp()
        doc = nlp(base)
        spans.extend(_spacy_spans(doc))
        signature_tokens.extend(_signature_from_doc(doc))
        spans = _dedupe_spans(spans)
        signature = tuple(dict.fromkeys(token for token in signature_tokens if token))
        return MessageAnalysis(spans=tuple(spans), signature=signature)

    def _get_nlp(self) -> Language:
        if self._nlp is not None:
            return self._nlp
        with self._nlp_lock:
            if self._nlp is not None:
                return self._nlp
            try:
                self._nlp = spacy.load(self._model_name)
            except OSError:
                try:
                    spacy_download(self._model_name)
                except SystemExit as download_exc:  # pragma: no cover - convert to informative error
                    raise RuntimeError(
                        (
                            f"spaCy model '{self._model_name}' is not installed and automatic download "
                            "failed. Install the model manually with 'python -m spacy download "
                            f"{self._model_name}' or set PYQA_NLP_MODEL to an available package."
                        ),
                    ) from download_exc
                self._nlp = spacy.load(self._model_name)
            except Exception as exc:  # pragma: no cover - fatal configuration issue
                raise RuntimeError(
                    (
                        f"spaCy model '{self._model_name}' could not be loaded; install the model "
                        "or set PYQA_NLP_MODEL to an available package."
                    ),
                ) from exc
            return self._nlp


SpanAdder = Callable[[int, int, str, HighlightKind | None], None]

_PATH_PATTERN = re.compile(r"((?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+(?:\.[A-Za-z0-9_]+)?)")
_CAMEL_CASE_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9]+")
_ARGUMENT_PATTERN = re.compile(r"function argument(?:s)?\s+([A-Za-z0-9_,\s]+)", re.IGNORECASE)
_VARIABLE_PATTERN = re.compile(r"variable(?:\s+name)?\s+([A-Za-z_][\w\.]*)", re.IGNORECASE)
_ATTRIBUTE_PATTERN = re.compile(r"attribute\s+[\"']([A-Za-z_][\w\.]*)[\"']", re.IGNORECASE)
_FUNCTION_INLINE_PATTERN = re.compile(r"function\s+([A-Za-z_][\w\.]*)", re.IGNORECASE)


def _heuristic_spans(message: str) -> tuple[list[MessageSpan], list[str]]:
    spans: list[MessageSpan] = []
    tokens: list[str] = []

    def add_span(start: int, end: int, style: str, kind: HighlightKind | None = None) -> None:
        if 0 <= start < end <= len(message):
            spans.append(MessageSpan(start=start, end=end, style=style, kind=kind))

    tokens.extend(_highlight_paths(message, add_span))
    tokens.extend(_highlight_camel_case(message, add_span))
    tokens.extend(_highlight_named_patterns(message, add_span))

    return spans, tokens


def _highlight_paths(message: str, add_span: SpanAdder) -> list[str]:
    tokens: list[str] = []
    for match in _PATH_PATTERN.finditer(message):
        start, end = match.start(1), match.end(1)
        value = message[start:end]
        tokens.append(value.lower())
        add_span(start, end, "ansi256:81", "file")
    return tokens


def _highlight_camel_case(message: str, add_span: SpanAdder) -> list[str]:
    tokens: list[str] = []
    for match in _CAMEL_CASE_PATTERN.finditer(message):
        value = match.group(0)
        if not _looks_camel_case(value):
            continue
        tokens.append(value.lower())
        add_span(match.start(0), match.end(0), "ansi256:154", "class")
    return tokens


def _highlight_named_patterns(message: str, add_span: SpanAdder) -> list[str]:
    tokens: list[str] = []
    tokens.extend(_highlight_function_arguments(message, add_span))
    tokens.extend(
        _highlight_simple_pattern(message, add_span, _VARIABLE_PATTERN, "ansi256:156", "variable")
    )
    tokens.extend(
        _highlight_simple_pattern(message, add_span, _ATTRIBUTE_PATTERN, "ansi256:208", "attribute")
    )
    tokens.extend(
        _highlight_simple_pattern(
            message, add_span, _FUNCTION_INLINE_PATTERN, "ansi256:208", "function"
        )
    )
    return tokens


def _highlight_function_arguments(message: str, add_span: SpanAdder) -> list[str]:
    tokens: list[str] = []
    for match in _ARGUMENT_PATTERN.finditer(message):
        raw_arguments = match.group(1)
        offset = match.start(1)
        for part in raw_arguments.split(","):
            name = part.strip(" \t.:;'\"")
            if not name:
                continue
            start = _find_token(message, name, offset)
            if start is None:
                continue
            tokens.append(name.lower())
            add_span(start, start + len(name), "ansi256:213", "argument")
            offset = start + len(name)
    return tokens


def _highlight_simple_pattern(
    message: str,
    add_span: SpanAdder,
    pattern: re.Pattern[str],
    style: str,
    kind_label: HighlightKind,
) -> list[str]:
    tokens: list[str] = []
    for match in pattern.finditer(message):
        name = match.group(1)
        start = match.start(1)
        tokens.append(name.lower())
        add_span(start, start + len(name), style, kind_label)
    return tokens


def _find_token(message: str, token: str, offset: int) -> int | None:
    index = message.find(token, offset)
    return None if index == -1 else index


def _spacy_spans(doc) -> list[MessageSpan]:  # type: ignore[no-untyped-def]
    spans: list[MessageSpan] = []
    for token in doc:
        if token.is_stop or not token.text.strip():
            continue
        if token.text[0].isupper() and token.text.isalpha():
            spans.append(
                MessageSpan(
                    token.idx,
                    token.idx + len(token.text),
                    "ansi256:154",
                    "class",
                ),
            )
        if token.pos_ in {"PROPN", "NOUN"} and token.text.isidentifier():
            spans.append(
                MessageSpan(
                    token.idx,
                    token.idx + len(token.text),
                    "ansi256:208",
                    "variable",
                ),
            )
    return spans


def _signature_from_doc(doc) -> list[str]:  # type: ignore[no-untyped-def]
    tokens: list[str] = []
    for token in doc:
        if token.is_stop or not token.text.strip():
            continue
        if token.pos_ in {"NOUN", "PROPN", "VERB", "ADJ"}:
            lemma = token.lemma_.lower().strip()
            if lemma:
                tokens.append(lemma)
    return tokens


def _looks_camel_case(token: str) -> bool:
    if len(token) < 2 or not token[0].isupper():
        return False
    if "_" in token:
        return False
    rest = token[1:]
    has_lower = any(ch.islower() for ch in rest)
    has_upper = any(ch.isupper() for ch in rest)
    return has_lower and has_upper


def _dedupe_spans(spans: Sequence[MessageSpan]) -> list[MessageSpan]:
    seen: list[MessageSpan] = []
    for span in sorted(spans, key=lambda s: (s.start, s.end - s.start), reverse=False):
        if any(_overlap(span, existing) for existing in seen):
            continue
        seen.append(span)
    return seen


def _overlap(left: MessageSpan, right: MessageSpan) -> bool:
    return max(left.start, right.start) < min(left.end, right.end)


__all__ = [
    "AnnotationEngine",
    "DiagnosticAnnotation",
    "MessageSpan",
]
