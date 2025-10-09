# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Analysis-oriented interfaces (Tree-sitter, spaCy, etc.)."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable

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
    """Lightweight structure describing a span highlighted in a message."""

    @property
    def start(self) -> int:
        """Return the inclusive start offset of the span."""

        raise NotImplementedError

    @property
    def end(self) -> int:
        """Return the exclusive end offset of the span."""

        raise NotImplementedError

    @property
    def style(self) -> str:
        """Return the presentation style hint for the span."""

        raise NotImplementedError

    @property
    def kind(self) -> str | None:
        """Return the semantic kind associated with the span."""

        raise NotImplementedError


@runtime_checkable
class AnnotationProvider(Protocol):
    """Protocol implemented by services that annotate diagnostic messages."""

    def annotate_run(self, result: Any) -> dict[int, Any]:
        """Annotate diagnostics contained within ``result``."""
        raise NotImplementedError

    def message_spans(self, message: str) -> Sequence[MessageSpan]:
        """Return spans detected in ``message``."""
        raise NotImplementedError

    def message_signature(self, message: str) -> Sequence[str]:
        """Return signature tokens derived from ``message``."""
        raise NotImplementedError


@runtime_checkable
class ContextResolver(Protocol):
    """Protocol describing Tree-sitter context resolution services."""

    def annotate(self, diagnostics: Iterable[Any], *, root: Path) -> None:
        """Populate contextual information on ``diagnostics``."""
        raise NotImplementedError

    def resolve_context_for_lines(
        self,
        file_path: str,
        *,
        root: Path,
        lines: Iterable[int],
    ) -> dict[int, str]:
        """Return contextual names keyed by requested line numbers."""
        raise NotImplementedError


@runtime_checkable
class FunctionScaleEstimator(Protocol):
    """Protocol for services that estimate function size and complexity."""

    @property
    def supported_languages(self) -> Sequence[str]:
        """Return languages this estimator can analyse."""
        raise NotImplementedError("FunctionScaleEstimator.supported_languages must be implemented")

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


__all__ = ["AnnotationProvider", "ContextResolver", "FunctionScaleEstimator", "MessageSpan"]


class NullAnnotationProvider(AnnotationProvider):
    """Annotation provider that returns empty structures for all requests."""

    def annotate_run(self, result: Any) -> dict[int, Any]:
        return {}

    def message_spans(self, message: str) -> Sequence[MessageSpan]:
        return (SimpleMessageSpan(start=0, end=0, style=""),)

    def message_signature(self, message: str) -> Sequence[str]:
        return ()


class NullContextResolver(ContextResolver):
    """Context resolver that performs no augmentation."""

    def annotate(self, diagnostics: Iterable[Any], *, root: Path) -> None:
        del diagnostics, root

    def resolve_context_for_lines(
        self,
        file_path: str,
        *,
        root: Path,
        lines: Iterable[int],
    ) -> dict[int, str]:
        del file_path, root, lines
        return {}


@dataclass(frozen=True, slots=True)
class SimpleMessageSpan(MessageSpan):
    """Concrete message span dataclass implementing the protocol."""

    start: int
    end: int
    style: str
    kind: str | None = None


__all__ = [
    "AnnotationProvider",
    "ContextResolver",
    "FunctionScaleEstimator",
    "HighlightKind",
    "MessageSpan",
    "SimpleMessageSpan",
    "NullAnnotationProvider",
    "NullContextResolver",
]
