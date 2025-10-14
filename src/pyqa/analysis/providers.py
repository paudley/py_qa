# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Lightweight analysis provider implementations used for testing and defaults."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path

from pyqa.core.models import Diagnostic, RunResult
from pyqa.interfaces.analysis import (
    AnnotationProvider,
    ContextResolver,
    DiagnosticAnnotation,
    MessageSpan,
)


class NullAnnotationProvider(AnnotationProvider):
    """Annotation provider that performs no enrichment."""

    def annotate_run(self, result: RunResult) -> dict[int, DiagnosticAnnotation]:
        """Return an empty annotation map for ``result``."""

        del result
        return {}

    def message_spans(self, message: str) -> Sequence[MessageSpan]:
        """Return an empty span sequence for ``message``."""

        del message
        return ()

    def message_signature(self, message: str) -> Sequence[str]:
        """Return an empty signature token sequence for ``message``."""

        del message
        return ()


class NullContextResolver(ContextResolver):
    """Context resolver that provides no additional diagnostic metadata."""

    def annotate(self, diagnostics: Iterable[Diagnostic], *, root: Path) -> None:
        """Ignore ``diagnostics`` leaving context unchanged."""

        del diagnostics, root

    def resolve_context_for_lines(
        self,
        file_path: str,
        *,
        root: Path,
        lines: Iterable[int],
    ) -> dict[int, str]:
        """Return an empty context mapping for ``file_path``."""

        del file_path, root, lines
        return {}


__all__ = ["NullAnnotationProvider", "NullContextResolver"]
