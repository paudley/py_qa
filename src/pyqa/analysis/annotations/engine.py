# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Annotation engine that combines heuristic, spaCy, and Tree-sitter data."""

from __future__ import annotations

import os
import re
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Final, Literal, cast

from pyqa.cache.in_memory import memoize

from ...core.logging import warn
from ...core.models import RunResult
from ...interfaces.analysis import (
    AnnotationProvider,
    ContextResolver,
    DiagnosticAnnotation,
    MessageSpan,
    SimpleMessageSpan,
)
from ..spacy.loader import SpacyLanguage, load_language
from ..spacy.message_spans import build_spacy_spans, iter_signature_tokens
from ..warnings import record_tool_warning

HighlightKind = Literal[
    "file",
    "function",
    "class",
    "argument",
    "variable",
    "attribute",
]

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
_FUNCTION_STYLE: Final[str] = "ansi256:208"
_MIN_CAMEL_LENGTH: Final[int] = 2
_UNDERSCORE_CHAR: Final[str] = "_"


@dataclass(frozen=True)
class MessageAnalysis:
    """Collect cached NLP artefacts for a diagnostic message."""

    spans: tuple[SimpleMessageSpan, ...]
    signature: tuple[str, ...]


class AnnotationEngine(AnnotationProvider):
    """Provide annotation logic that leverages Tree-sitter and spaCy."""

    def __init__(
        self,
        model: str | None = None,
        *,
        context_resolver: ContextResolver | None = None,
        loader: Callable[[str], SpacyLanguage | None] = load_language,
    ) -> None:
        """Initialise the annotation engine.

        Args:
            model: Preferred spaCy model name when automatically loading.
            context_resolver: Optional Tree-sitter resolver used for symbol lookup.
            loader: Function responsible for producing a spaCy pipeline.
        """
        env_model = os.getenv("PYQA_NLP_MODEL")
        self._model_name: str = model or env_model or "en_core_web_sm"
        self._loader = loader
        self._nlp: SpacyLanguage | None = None
        self._nlp_lock = threading.Lock()
        if context_resolver is None:
            raise ValueError("AnnotationEngine requires a context_resolver instance")
        self._resolver = context_resolver
        self._download_attempted = False
        self._nlp_missing = False

    def annotate_run(self, result: RunResult) -> dict[int, DiagnosticAnnotation]:
        """Annotate the diagnostics contained in the run result.

        Args:
            result: Aggregated lint outcome produced by the orchestrator.

        Returns:
            dict[int, DiagnosticAnnotation]: Mapping of diagnostic identifiers to
            enriched annotation metadata.
        """

        annotations: dict[int, DiagnosticAnnotation] = {}
        self._nlp_missing = False
        self._resolver.annotate(
            (diag for outcome in result.outcomes for diag in outcome.diagnostics),
            root=result.root,
        )
        for message in getattr(self._resolver, "consume_warnings", lambda: [])():
            record_tool_warning(result, message)
        for outcome in result.outcomes:
            for diag in outcome.diagnostics:
                analysis = self._analyse_message(diag.message)
                annotations[id(diag)] = DiagnosticAnnotation(
                    function=diag.function,
                    class_name=None,
                    message_spans=analysis.spans,
                )
        if self._nlp_missing:
            message = f"spaCy model '{self._model_name}' unavailable; docstring and annotation features are degraded."
            warn(message, use_emoji=True)
            record_tool_warning(result, message)
        return annotations

    def message_spans(self, message: str) -> Sequence[MessageSpan]:
        """Analyze highlight spans detected within the message.

        Args:
            message: Diagnostic text to analyse.

        Returns:
            Sequence[MessageSpan]: Span metadata describing highlighted
            regions detected within the message.
        """

        analysis = self._analyse_message(message)
        return analysis.spans

    def message_signature(self, message: str) -> Sequence[str]:
        """Return the semantic signature extracted from the message.

        Args:
            message: Diagnostic text to transform into semantic tokens.

        Returns:
            Sequence[str]: Ordered collection of tokens representing the
            diagnostic semantics for the message.
        """

        return self._analyse_message(message).signature

    @memoize(maxsize=2048)
    def _analyse_message(self, message: str) -> MessageAnalysis:
        """Return message analysis using heuristics and spaCy when available.

        Args:
            message: Diagnostic text under analysis.

        Returns:
            MessageAnalysis: Cached spans and signature tokens.
        """

        base = message
        spans: list[SimpleMessageSpan] = []
        signature_tokens: list[str] = []
        heuristic_spans, heuristic_tokens = _heuristic_spans(base)
        spans.extend(heuristic_spans)
        signature_tokens.extend(heuristic_tokens)
        nlp = self._get_nlp()
        if nlp is not None:
            doc = nlp(base)
            spans.extend(build_spacy_spans(doc, _build_span))
            signature_tokens.extend(iter_signature_tokens(doc))
        else:
            self._nlp_missing = True
            signature_tokens.extend(_fallback_signature_tokens(base))
        spans = _dedupe_spans(spans)
        signature = tuple(dict.fromkeys(token for token in signature_tokens if token))
        return MessageAnalysis(spans=tuple(spans), signature=signature)

    def _get_nlp(self) -> SpacyLanguage | None:
        """Return the cached spaCy pipeline, downloading the model if required.

        Returns:
            SpacyLanguage | None: Cached NLP pipeline if available; otherwise ``None``
            when spaCy support is not installed or the model download failed.
        """

        if self._nlp is not None:
            return self._nlp
        with self._nlp_lock:
            if self._nlp is None:
                self._nlp = self._initialise_spacy_model(self._model_name)
            return self._nlp

    def _initialise_spacy_model(self, model_name: str) -> SpacyLanguage | None:
        """Load the requested spaCy pipeline, attempting install when necessary.

        Args:
            model_name: Fully qualified spaCy model identifier.

        Returns:
            SpacyLanguage | None: Loaded pipeline instance or ``None`` when loading
            is not possible.
        """
        if self._download_attempted:
            return self._loader(model_name)
        pipeline = self._loader(model_name)
        if pipeline is not None:
            return pipeline
        self._download_attempted = True
        return self._loader(model_name)


@dataclass(slots=True)
class _SpanSpec:
    """Describe a span style and highlight kind."""

    style: str
    kind: HighlightKind


_PATH_SPEC: Final[_SpanSpec] = _SpanSpec(style=_PATH_STYLE, kind="file")
_CLASS_SPEC: Final[_SpanSpec] = _SpanSpec(style=_CLASS_STYLE, kind="class")
_ARGUMENT_SPEC: Final[_SpanSpec] = _SpanSpec(style=_ARGUMENT_STYLE, kind="argument")
_VARIABLE_SPEC: Final[_SpanSpec] = _SpanSpec(style=_VARIABLE_STYLE, kind="variable")
_ATTRIBUTE_SPEC: Final[_SpanSpec] = _SpanSpec(style=_ATTRIBUTE_STYLE, kind="attribute")
_FUNCTION_SPEC: Final[_SpanSpec] = _SpanSpec(style=_FUNCTION_STYLE, kind="function")


def _build_span(start: int, end: int, style: str, kind: str | None) -> SimpleMessageSpan:
    """Create a simple message span for spaCy-driven highlights.

    Args:
        start: Inclusive span starting offset within the analysed message.
        end: Exclusive span ending offset within the analysed message.
        style: Rendering style applied to the highlighted span.
        kind: Optional semantic kind describing the highlight purpose.

    Returns:
        SimpleMessageSpan: Concrete span dataclass used to satisfy the span protocol.
    """

    highlight_kind = cast(HighlightKind | None, kind)
    return SimpleMessageSpan(start=start, end=end, style=style, kind=highlight_kind)


def _heuristic_spans(message: str) -> tuple[list[SimpleMessageSpan], list[str]]:
    """Return heuristic spans and signature tokens from the diagnostic message.

    Args:
        message: Diagnostic message text awaiting annotation.

    Returns:
        tuple[list[SimpleMessageSpan], list[str]]: Pairs of spans and associated tokens
        derived from quick heuristics before spaCy enrichment.
    """

    collector = _SpanCollector(message=message, spans=[], tokens=[])
    collector.collect()
    return collector.spans, collector.tokens


@dataclass(slots=True)
class _SpanCollector:
    """Collect span candidates for heuristic annotation passes."""

    message: str
    spans: list[SimpleMessageSpan]
    tokens: list[str]

    def collect(self) -> None:
        """Collect span and token candidates using heuristic rules."""

        self._collect_paths()
        self._collect_camel_case_identifiers()
        self._collect_argument_names()
        self._collect_simple_matches(_VARIABLE_PATTERN, _VARIABLE_SPEC)
        self._collect_simple_matches(_ATTRIBUTE_PATTERN, _ATTRIBUTE_SPEC)
        self._collect_simple_matches(_FUNCTION_PATTERN, _FUNCTION_SPEC)

    def _collect_paths(self) -> None:
        """Collect filesystem path spans within the message text."""

        for match in _PATH_PATTERN.finditer(self.message):
            value = self.message[match.start(1) : match.end(1)]
            self._record_span(value, match.start(1), match.end(1), _PATH_SPEC)

    def _collect_camel_case_identifiers(self) -> None:
        """Collect CamelCase identifiers in the message text."""

        for match in _CAMEL_IDENTIFIER_PATTERN.finditer(self.message):
            value = match.group(0)
            if _looks_camel_case(value):
                self._record_span(value, match.start(0), match.end(0), _CLASS_SPEC)

    def _collect_argument_names(self) -> None:
        """Collect function argument name spans within the message."""

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
        """Capture simple regex-based span matches.

        Args:
            pattern: Compiled regular expression describing the match.
            spec: Span styling metadata applied to each match.
        """

        for match in pattern.finditer(self.message):
            name = match.group(1)
            self._record_span(name, match.start(1), match.end(1), spec)

    @staticmethod
    def _split_arguments(raw_arguments: str) -> list[str]:
        """Collect argument names from the raw capture group.

        Args:
            raw_arguments: Raw string containing argument names and punctuation.

        Returns:
            list[str]: Sanitised argument names extracted from the capture group.
        """

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
        """Persist a span and token for the supplied match data.

        Args:
            value: Raw token value extracted from the message.
            start: Inclusive starting offset of the span.
            end: Exclusive ending offset of the span.
            spec: Styling metadata used to format the span.
        """

        if 0 <= start < end <= len(self.message):
            self.tokens.append(value.lower())
            self.spans.append(
                SimpleMessageSpan(start=start, end=end, style=spec.style, kind=spec.kind),
            )


def _fallback_signature_tokens(message: str) -> list[str]:
    """Derive simple semantic tokens when spaCy is unavailable.

    Args:
        message: Diagnostic message text awaiting tokenisation.

    Returns:
        list[str]: Lowercased tokens extracted via a conservative heuristic.
    """

    return re.findall(r"[a-zA-Z_]{3,}", message.lower())


def _looks_camel_case(token: str) -> bool:
    """Return True when the token resembles a CamelCase identifier.

    Args:
        token: Candidate token to evaluate.

    Returns:
        bool: ``True`` if the token matches CamelCase heuristics.
    """

    if len(token) < _MIN_CAMEL_LENGTH or not token[0].isupper():
        return False
    if _UNDERSCORE_CHAR in token:
        return False
    rest = token[1:]
    has_lower = any(ch.islower() for ch in rest)
    has_upper = any(ch.isupper() for ch in rest)
    return has_lower and has_upper


def _dedupe_spans(spans: Sequence[SimpleMessageSpan]) -> list[SimpleMessageSpan]:
    """Remove overlapping spans to keep unique highlights.

    Args:
        spans: Candidate spans generated via heuristic and NLP passes.

    Returns:
        list[SimpleMessageSpan]: De-duplicated spans sorted by position and size.
    """

    seen: list[SimpleMessageSpan] = []
    for span in sorted(spans, key=lambda s: (s.start, s.end - s.start)):
        if any(_overlap(span, existing) for existing in seen):
            continue
        seen.append(span)
    return seen


def _overlap(left: SimpleMessageSpan, right: SimpleMessageSpan) -> bool:
    """Return True when span ranges intersect.

    Args:
        left: First span under consideration.
        right: Second span under consideration.

    Returns:
        bool: ``True`` if the spans overlap.
    """

    return max(left.start, right.start) < min(left.end, right.end)


__all__ = [
    "AnnotationEngine",
    "DiagnosticAnnotation",
    "MessageAnalysis",
    "MessageSpan",
]
