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
import subprocess
import threading
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from functools import lru_cache
from shutil import which
from typing import Final, Literal, Protocol, cast, runtime_checkable

import spacy

from .context import TreeSitterContextResolver
from .models import RunResult


@runtime_checkable
class TokenLike(Protocol):
    """Protocol describing the spaCy token API relied upon by pyqa."""

    @property
    def text(self) -> str:  # pragma: no cover - protocol definition
        """Return the raw token text as emitted by spaCy."""
        ...

    @property
    def idx(self) -> int:  # pragma: no cover - protocol definition
        """Return the byte index of the token within the source string."""
        ...

    @property
    def is_stop(self) -> bool:  # pragma: no cover - protocol definition
        """Return ``True`` when the token is considered a stop word."""
        ...

    @property
    def pos_(self) -> str:  # pragma: no cover - protocol definition
        """Return the coarse-grained part-of-speech tag for the token."""
        ...

    @property
    def lemma_(self) -> str:  # pragma: no cover - protocol definition
        """Return the lemmatised form of the token."""
        ...

    def __len__(self) -> int:  # pragma: no cover - protocol definition
        """Return the character length of the token."""
        ...


@runtime_checkable
class DocLike(Protocol):
    """Protocol representing iterable spaCy documents used in analysis."""

    def __iter__(self) -> Iterator[TokenLike]:  # pragma: no cover - protocol definition
        """Yield ``TokenLike`` instances from the parsed document."""
        ...

    def __len__(self) -> int:  # pragma: no cover - protocol definition
        """Return the number of tokens contained in the document."""
        ...

    def __getitem__(self, index: int) -> TokenLike:  # pragma: no cover - protocol definition
        """Return a token located at ``index`` within the document."""
        ...


_PATH_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"((?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+(?:\.[A-Za-z0-9_]+)?)",
)
_CAMEL_IDENTIFIER_PATTERN: Final[re.Pattern[str]] = re.compile(r"[A-Za-z][A-Za-z0-9]+")
_ARGUMENT_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"function argument(?:s)?\s+([A-Za-z0-9_,\s]+)",
    re.IGNORECASE,
)
_VARIABLE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"variable(?:\s+name)?\s+([A-Za-z_][\w\.]*)",
    re.IGNORECASE,
)
_ATTRIBUTE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"attribute\s+[\"']([A-Za-z_][\w\.]*)[\"']",
    re.IGNORECASE,
)
_FUNCTION_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"function\s+([A-Za-z_][\w\.]*)",
    re.IGNORECASE,
)

_PATH_STYLE: Final[str] = "ansi256:81"
_CLASS_STYLE: Final[str] = "ansi256:154"
_ARGUMENT_STYLE: Final[str] = "ansi256:213"
_VARIABLE_STYLE: Final[str] = "ansi256:156"
_ATTRIBUTE_STYLE: Final[str] = "ansi256:208"
_MIN_CAMEL_LENGTH: Final[int] = 2
_UNDERSCORE_CHAR: Final[str] = "_"


@dataclass(frozen=True, slots=True)
class _SpanSpec:
    """Describe a span style and highlight kind."""

    style: str
    kind: HighlightKind


_PATH_SPEC: Final[_SpanSpec] = _SpanSpec(style=_PATH_STYLE, kind="file")
_CLASS_SPEC: Final[_SpanSpec] = _SpanSpec(style=_CLASS_STYLE, kind="class")
_ARGUMENT_SPEC: Final[_SpanSpec] = _SpanSpec(style=_ARGUMENT_STYLE, kind="argument")
_VARIABLE_SPEC: Final[_SpanSpec] = _SpanSpec(style=_VARIABLE_STYLE, kind="variable")
_ATTRIBUTE_SPEC: Final[_SpanSpec] = _SpanSpec(style=_ATTRIBUTE_STYLE, kind="attribute")
_FUNCTION_SPEC: Final[_SpanSpec] = _SpanSpec(style=_ATTRIBUTE_STYLE, kind="function")


class SpacyLanguage(Protocol):
    """Callable NLP pipeline contract used by pyqa."""

    def __call__(self, text: str) -> DocLike:  # pragma: no cover - protocol definition
        """Return a parsed document for ``text``."""
        ...

    def pipe(self, texts: Iterable[str]) -> Iterable[DocLike]:  # pragma: no cover - protocol definition
        """Yield parsed documents for a stream of input strings."""
        ...


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
        self._nlp: SpacyLanguage | None = None
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

    def _get_nlp(self) -> SpacyLanguage | None:
        if self._nlp is not None:
            return self._nlp
        with self._nlp_lock:
            if self._nlp is not None:
                return self._nlp
            try:
                self._nlp = cast(SpacyLanguage, spacy.load(self._model_name))
            except OSError:  # pragma: no cover - spaCy optional
                should_retry = False
                if not self._download_attempted:
                    self._download_attempted = True
                    should_retry = _download_spacy_model(self._model_name)
                if should_retry:
                    try:
                        self._nlp = cast(SpacyLanguage, spacy.load(self._model_name))
                    except OSError:
                        self._nlp = None
                else:
                    self._nlp = None
            return self._nlp


def _heuristic_spans(message: str) -> tuple[list[MessageSpan], list[str]]:
    """Return heuristic spans/token hints derived from ``message``.

    Args:
        message: Diagnostic message emitted by a tool.

    Returns:
        tuple[list[MessageSpan], list[str]]: Highlight spans and lower-cased
        tokens extracted from ``message`` using lightweight regex heuristics.
    """

    collector = _SpanCollector(message=message, spans=[], tokens=[])
    collector.collect()
    return collector.spans, collector.tokens


@dataclass(slots=True)
class _SpanCollector:
    """Utility for extracting highlight spans and associated tokens."""

    message: str
    spans: list[MessageSpan]
    tokens: list[str]

    def collect(self) -> None:
        """Populate ``spans`` and ``tokens`` using heuristic patterns."""

        self._collect_paths()
        self._collect_camel_case_identifiers()
        self._collect_argument_names()
        self._collect_simple_matches(_VARIABLE_PATTERN, _VARIABLE_SPEC)
        self._collect_simple_matches(_ATTRIBUTE_PATTERN, _ATTRIBUTE_SPEC)
        self._collect_simple_matches(_FUNCTION_PATTERN, _FUNCTION_SPEC)

    # Span helpers -----------------------------------------------------------------

    def _collect_paths(self) -> None:
        """Highlight path-like substrings within the message."""

        for match in _PATH_PATTERN.finditer(self.message):
            value = self.message[match.start(1) : match.end(1)]
            self._record_span(value, match.start(1), match.end(1), _PATH_SPEC)

    def _collect_camel_case_identifiers(self) -> None:
        """Highlight CamelCase identifiers that resemble class names."""

        for match in _CAMEL_IDENTIFIER_PATTERN.finditer(self.message):
            value = match.group(0)
            if _looks_camel_case(value):
                self._record_span(value, match.start(0), match.end(0), _CLASS_SPEC)

    def _collect_argument_names(self) -> None:
        """Highlight function argument names referenced inline."""

        for match in _ARGUMENT_PATTERN.finditer(self.message):
            raw_arguments = match.group(1)
            search_start = match.start(1)
            for name in self._split_arguments(raw_arguments):
                start = self.message.find(name, search_start)
                if start == -1:
                    continue
                end = start + len(name)
                self._record_span(name, start, end, _ARGUMENT_SPEC)
                search_start = end

    def _collect_simple_matches(
        self,
        pattern: re.Pattern[str],
        spec: _SpanSpec,
    ) -> None:
        """Highlight matches using ``pattern`` with a uniform style/kind."""

        for match in pattern.finditer(self.message):
            name = match.group(1)
            self._record_span(name, match.start(1), match.end(1), spec)

    # Utility helpers --------------------------------------------------------------

    @staticmethod
    def _split_arguments(raw_arguments: str) -> list[str]:
        """Return cleaned argument names extracted from ``raw_arguments``."""

        cleaned: list[str] = []
        for part in raw_arguments.split(","):
            name = part.strip(" \t.:;'\"")
            if name:
                cleaned.append(name)
        return cleaned

    def _record_span(
        self,
        value: str,
        start: int,
        end: int,
        spec: _SpanSpec,
    ) -> None:
        """Store the lower-cased token and its highlight span."""

        if 0 <= start < end <= len(self.message):
            self.tokens.append(value.lower())
            self.spans.append(
                MessageSpan(start=start, end=end, style=spec.style, kind=spec.kind),
            )


def _spacy_spans(doc: DocLike) -> list[MessageSpan]:
    """Return spaCy-derived highlight spans for the supplied document.

    Args:
        doc: spaCy document produced by the configured language pipeline.

    Returns:
        list[MessageSpan]: Highlight spans inferred from part-of-speech tags
        and casing heuristics.

    """

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


def _signature_from_doc(doc: DocLike) -> list[str]:
    """Return semantic signature tokens extracted from ``doc``.

    Args:
        doc: spaCy document produced by the configured language pipeline.

    Returns:
        list[str]: Lemmas capturing the key nouns, verbs, and adjectives in the
        message.

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


def _fallback_signature_tokens(message: str) -> list[str]:
    """Return naive signature tokens when spaCy is unavailable.

    Args:
        message: Diagnostic message to tokenise.

    Returns:
        list[str]: Lower-cased tokens with minimal length filtering applied.

    """

    return re.findall(r"[a-zA-Z_]{3,}", message.lower())


def _looks_camel_case(token: str) -> bool:
    """Return ``True`` when ``token`` resembles a CamelCase identifier.

    Args:
        token: Identifier candidate taken from a diagnostic message.

    Returns:
        bool: ``True`` when the token appears to be CamelCase.

    """

    if len(token) < _MIN_CAMEL_LENGTH or not token[0].isupper():
        return False
    if _UNDERSCORE_CHAR in token:
        return False
    rest = token[1:]
    has_lower = any(ch.islower() for ch in rest)
    has_upper = any(ch.isupper() for ch in rest)
    return has_lower and has_upper


def _dedupe_spans(spans: Sequence[MessageSpan]) -> list[MessageSpan]:
    """Return ``spans`` without overlaps, preferring earlier entries.

    Args:
        spans: Candidate spans produced by heuristics and spaCy analysis.

    Returns:
        list[MessageSpan]: Non-overlapping set of spans sorted by position.

    """

    seen: list[MessageSpan] = []
    for span in sorted(spans, key=lambda s: (s.start, s.end - s.start), reverse=False):
        if any(_overlap(span, existing) for existing in seen):
            continue
        seen.append(span)
    return seen


def _overlap(left: MessageSpan, right: MessageSpan) -> bool:
    """Return ``True`` when two message spans overlap.

    Args:
        left: First span for overlap comparison.
        right: Second span for overlap comparison.

    Returns:
        bool: ``True`` when the spans intersect.

    """

    return max(left.start, right.start) < min(left.end, right.end)


def _download_spacy_model(model_name: str) -> bool:
    """Attempt to download the specified spaCy model via ``uv``.

    Args:
        model_name: Name of the spaCy model to fetch from the model releases.

    Returns:
        bool: ``True`` when the model download succeeds, otherwise ``False``.

    """

    uv_path = which("uv")
    if not uv_path:
        return False

    version = getattr(spacy, "__version__", None)
    if not version:
        return False

    url = (
        "https://github.com/explosion/spacy-models/releases/download/"
        f"{model_name}-{version}/{model_name}-{version}-py3-none-any.whl"
    )

    try:
        completed = subprocess.run(
            [uv_path, "pip", "install", url],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return False

    if completed.returncode != 0:
        return False

    return True


__all__ = [
    "AnnotationEngine",
    "DiagnosticAnnotation",
    "MessageSpan",
]
