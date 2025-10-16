# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Organise analysis-oriented protocols (Tree-sitter, spaCy, etc.)."""

from __future__ import annotations

from abc import abstractmethod
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

from pyqa.core.models import Diagnostic, RunResult

HighlightKind = Literal[
    "file",
    "function",
    "class",
    "argument",
    "variable",
    "attribute",
]


@runtime_checkable
class MessageSpan(Protocol):
    """Provide a read-only view of a highlighted span extracted from a message."""

    @property
    @abstractmethod
    def start(self) -> int:
        """Return the inclusive start offset of the span.

        Returns:
            int: Inclusive start offset expressed as a character index.
        """
        raise NotImplementedError("MessageSpan.start must be implemented")

    @property
    @abstractmethod
    def end(self) -> int:
        """Return the exclusive end offset of the span.

        Returns:
            int: Exclusive end offset expressed as a character index.
        """
        raise NotImplementedError("MessageSpan.end must be implemented")

    @property
    @abstractmethod
    def style(self) -> str:
        """Return the highlighting style applied to the span.

        Returns:
            str: Highlight style identifier supplied by the annotation provider.
        """
        raise NotImplementedError("MessageSpan.style must be implemented")

    @property
    @abstractmethod
    def kind(self) -> str | None:
        """Return the semantic kind associated with the span when available.

        Returns:
            str | None: Semantic kind string or ``None`` when unspecified.
        """
        raise NotImplementedError("MessageSpan.kind must be implemented")


@runtime_checkable
class AnnotationProvider(Protocol):
    """Provide annotation services for diagnostic messages."""

    @abstractmethod
    def annotate_run(self, result: RunResult) -> Mapping[int, DiagnosticAnnotation]:
        """Provide annotations for diagnostics contained within ``result``.

        Args:
            result: Aggregated lint output to enrich.

        Returns:
            Mapping[int, DiagnosticAnnotation]: Annotation payloads keyed by diagnostic identifier.
        """
        raise NotImplementedError

    @abstractmethod
    def message_spans(self, message: str) -> Sequence[MessageSpan]:
        """Produce highlight spans detected within ``message``.

        Args:
            message: Diagnostic message requiring highlight extraction.

        Returns:
            Sequence[MessageSpan]: Ordered spans referencing highlighted tokens.
        """
        raise NotImplementedError

    @abstractmethod
    def message_signature(self, message: str) -> Sequence[str]:
        """Generate signature tokens that describe ``message`` semantics.

        Args:
            message: Diagnostic message that should be tokenised.

        Returns:
            Sequence[str]: Ordered signature tokens used for classification.
        """
        raise NotImplementedError


@runtime_checkable
class ContextResolver(Protocol):
    """Deliver structural context resolution for diagnostics."""

    @abstractmethod
    def annotate(self, diagnostics: Iterable[Diagnostic], *, root: Path) -> None:
        """Inject contextual information onto ``diagnostics``.

        Args:
            diagnostics: Iterable of diagnostics to annotate in place.
            root: Repository root used for filesystem lookups.
        """
        raise NotImplementedError

    @abstractmethod
    def resolve_context_for_lines(
        self,
        file_path: str,
        *,
        root: Path,
        lines: Iterable[int],
    ) -> dict[int, str]:
        """Resolve contextual names keyed by the requested line numbers.

        Args:
            file_path: File path subject to context resolution.
            root: Repository root used to resolve relative paths.
            lines: One-based line numbers for which context is required.

        Returns:
            dict[int, str]: Mapping of line numbers to resolved context strings.
        """
        raise NotImplementedError


@runtime_checkable
class FunctionScaleEstimator(Protocol):
    """Provide estimates for function size and cyclomatic complexity."""

    @property
    @abstractmethod
    def supported_languages(self) -> Sequence[str]:
        """Return the languages that the estimator can analyse.

        Returns:
            Sequence[str]: Language identifiers the estimator supports.
        """
        raise NotImplementedError

    @abstractmethod
    def estimate(self, path: Path, function: str) -> tuple[int | None, int | None]:
        """Return approximate line count and complexity for ``function``.

        Args:
            path: Filesystem path to the module containing ``function``.
            function: Fully qualified function name (without module path).

        Returns:
            tuple[int | None, int | None]: Estimated line count and complexity
            score, or ``None`` for values that cannot be computed.
        """
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class SimpleMessageSpan(MessageSpan):
    """Represent a message span implementing :class:`MessageSpan`."""

    _start: int
    _end: int
    _style: str
    _kind: str | None = None

    def __init__(self, start: int, end: int, style: str, kind: str | None = None) -> None:
        """Initialise a simple message span instance.

        Args:
            start: Inclusive start offset of the span.
            end: Exclusive end offset of the span.
            style: Highlight style identifier.
            kind: Optional semantic kind associated with the span.
        """

        object.__setattr__(self, "_start", start)
        object.__setattr__(self, "_end", end)
        object.__setattr__(self, "_style", style)
        object.__setattr__(self, "_kind", kind)

    @property
    def start(self) -> int:
        """Return the inclusive start offset captured by the span.

        Returns:
            int: Inclusive start offset expressed as a zero-based character index.
        """
        return self._start

    @property
    def end(self) -> int:
        """Return the exclusive end offset captured by the span.

        Returns:
            int: Exclusive end offset expressed as a zero-based character index.
        """
        return self._end

    @property
    def style(self) -> str:
        """Return the styling identifier describing how to render the span.

        Returns:
            str: Highlighting style associated with the span.
        """
        return self._style

    @property
    def kind(self) -> str | None:
        """Return the semantic kind linked to the span when provided.

        Returns:
            str | None: Semantic tag describing the span; ``None`` when unspecified.
        """
        return self._kind


@dataclass(frozen=True, slots=True)
class DiagnosticAnnotation:
    """Maintain annotation metadata attached to a diagnostic message."""

    function: str | None
    class_name: str | None
    message_spans: tuple[SimpleMessageSpan, ...]


__all__ = [
    "AnnotationProvider",
    "ContextResolver",
    "FunctionScaleEstimator",
    "HighlightKind",
    "MessageSpan",
    "SimpleMessageSpan",
    "DiagnosticAnnotation",
]
