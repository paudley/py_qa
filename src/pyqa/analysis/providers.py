# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Lightweight analysis provider implementations used for testing and defaults."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from pyqa.interfaces.analysis import AnnotationProvider, ContextResolver, MessageSpan, SimpleMessageSpan


class NullAnnotationProvider(AnnotationProvider):
    """Annotation provider that returns empty results for all requests."""

    def annotate_run(self, result: Any) -> dict[int, Any]:
        return {}

    def message_spans(self, message: str) -> Sequence[MessageSpan]:
        return (SimpleMessageSpan(start=0, end=0, style=""),)

    def message_signature(self, message: str) -> Sequence[str]:
        return ()


class NullContextResolver(ContextResolver):
    """Context resolver that provides no additional diagnostic metadata."""

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


__all__ = ["NullAnnotationProvider", "NullContextResolver"]
