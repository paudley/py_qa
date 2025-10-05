"""Analysis-oriented interfaces (Tree-sitter, spaCy, etc.)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable
from collections.abc import Sequence


class MessageSpan(Protocol):
    """Lightweight structure describing a span highlighted in a message."""

    start: int
    end: int
    kind: str


@runtime_checkable
class AnnotationProvider(Protocol):
    """Protocol implemented by services that annotate diagnostic messages."""

    def message_spans(self, message: str) -> Sequence[MessageSpan]:
        """Return spans detected in ``message``."""
        ...
