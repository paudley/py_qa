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
import threading
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

from .context import TreeSitterContextResolver
from .models import RunResult

try:
    import spacy  # type: ignore[import]
    from spacy.language import Language
except Exception:  # pragma: no cover - optional dependency may be missing
    spacy = None
    Language = None  # type: ignore


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
        self._model_name = model or os.getenv("PYQA_NLP_MODEL", "en_core_web_sm")
        self._nlp: Language | None = None
        self._nlp_lock = threading.Lock()
        self._resolver = TreeSitterContextResolver()
        self._download_attempted = False

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

    @lru_cache(maxsize=2048)
    def _analyse_message(self, message: str) -> MessageAnalysis:
        base = message
        spans: list[MessageSpan] = []
        signature_tokens: list[str] = []
        heuristic_spans, heuristic_tokens = _heuristic_spans(base)
        spans.extend(heuristic_spans)
        signature_tokens.extend(heuristic_tokens)
        nlp = self._get_nlp()
        if nlp is not None:
            doc = nlp(base)
            spans.extend(_spacy_spans(doc))
            signature_tokens.extend(_signature_from_doc(doc))
        else:
            signature_tokens.extend(_fallback_signature_tokens(base))
        spans = _dedupe_spans(spans)
        signature = tuple(dict.fromkeys(token for token in signature_tokens if token))
        return MessageAnalysis(spans=tuple(spans), signature=signature)

    def _get_nlp(self) -> Language | None:
        if spacy is None:
            return None
        if self._nlp is not None:
            return self._nlp
        with self._nlp_lock:
            if self._nlp is not None:
                return self._nlp
            try:
                self._nlp = spacy.load(self._model_name)
            except Exception:  # pragma: no cover - spaCy optional
                should_retry = False
                if not self._download_attempted:
                    self._download_attempted = True
                    should_retry = _download_spacy_model(self._model_name)
                if should_retry:
                    try:
                        self._nlp = spacy.load(self._model_name)
                    except Exception:
                        self._nlp = None
                else:
                    self._nlp = None
            return self._nlp


def _heuristic_spans(message: str) -> tuple[list[MessageSpan], list[str]]:
    spans: list[MessageSpan] = []
    tokens: list[str] = []
    import re

    def add_span(start: int, end: int, style: str, kind: HighlightKind | None = None) -> None:
        if 0 <= start < end <= len(message):
            spans.append(MessageSpan(start=start, end=end, style=style, kind=kind))

    path_pattern = re.compile(
        r"((?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+(?:\.[A-Za-z0-9_]+)?)",
    )
    for match in path_pattern.finditer(message):
        value = message[match.start(1) : match.end(1)]
        tokens.append(value.lower())
        add_span(match.start(1), match.end(1), "ansi256:81", "file")

    for match in re.finditer(r"[A-Za-z][A-Za-z0-9]+", message):
        value = match.group(0)
        if _looks_camel_case(value):
            tokens.append(value.lower())
            add_span(match.start(0), match.end(0), "ansi256:154", "class")

    argument_pattern = re.compile(r"function argument(?:s)?\s+([A-Za-z0-9_,\s]+)", re.IGNORECASE)
    variable_pattern = re.compile(r"variable(?:\s+name)?\s+([A-Za-z_][\w\.]*)", re.IGNORECASE)
    attribute_pattern = re.compile(r"attribute\s+[\"']([A-Za-z_][\w\.]*)[\"']", re.IGNORECASE)
    function_inline_pattern = re.compile(r"function\s+([A-Za-z_][\w\.]*)", re.IGNORECASE)

    for match in argument_pattern.finditer(message):
        raw = match.group(1)
        offset = match.start(1)
        for part in raw.split(","):
            name = part.strip(" \t.:;'\"")
            if not name:
                continue
            start = message.find(name, offset)
            if start == -1:
                continue
            tokens.append(name.lower())
            add_span(start, start + len(name), "ansi256:213", "argument")
            offset = start + len(name)

    for match in variable_pattern.finditer(message):
        name = match.group(1)
        start = match.start(1)
        tokens.append(name.lower())
        add_span(start, start + len(name), "ansi256:156", "variable")

    for match in attribute_pattern.finditer(message):
        name = match.group(1)
        start = match.start(1)
        tokens.append(name.lower())
        add_span(start, start + len(name), "ansi256:208", "attribute")

    for match in function_inline_pattern.finditer(message):
        name = match.group(1)
        start = match.start(1)
        tokens.append(name.lower())
        add_span(start, start + len(name), "ansi256:208", "function")

    return spans, tokens


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


def _fallback_signature_tokens(message: str) -> list[str]:
    import re

    return re.findall(r"[a-zA-Z_]{3,}", message.lower())


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


def _download_spacy_model(model_name: str) -> bool:
    if spacy is None:
        return False
    try:
        from spacy.cli import download  # type: ignore[import]
    except Exception:  # pragma: no cover - spaCy optional command missing
        return False
    try:
        download(model_name)  # type: ignore[call-arg]
        return True
    except BaseException:  # pragma: no cover - network or install issue / SystemExit
        return False


__all__ = [
    "AnnotationEngine",
    "DiagnosticAnnotation",
    "MessageSpan",
]
