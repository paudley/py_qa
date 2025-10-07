# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Analysis-oriented interfaces (Tree-sitter, spaCy, etc.)."""

# pylint: disable=too-few-public-methods -- Protocol definitions intentionally expose minimal method surfaces.

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class MessageSpan(Protocol):
    """Lightweight structure describing a span highlighted in a message."""

    start: int
    end: int
    kind: str
    style: str


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
