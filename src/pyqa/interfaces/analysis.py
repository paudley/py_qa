# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Analysis-oriented interfaces (Tree-sitter, spaCy, etc.)."""

# pylint: disable=too-few-public-methods

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable


@runtime_checkable
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
        raise NotImplementedError
