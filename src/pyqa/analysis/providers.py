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
    """Implement a no-op annotation provider."""

    def annotate_run(self, result: RunResult) -> dict[int, DiagnosticAnnotation]:
        """Return an empty annotation map for ``result``.

        Args:
            result: Aggregated lint outcome supplied by the orchestrator.

        Returns:
            dict[int, DiagnosticAnnotation]: Always an empty mapping.
        """

        del result
        return {}

    def message_spans(self, message: str) -> Sequence[MessageSpan]:
        """Return an empty span sequence for ``message``.

        Args:
            message: Diagnostic text that would otherwise be analysed.

        Returns:
            Sequence[MessageSpan]: Always an empty tuple of spans.
        """

        del message
        return ()

    def message_signature(self, message: str) -> Sequence[str]:
        """Return an empty signature token sequence for ``message``.

        Args:
            message: Diagnostic text that would otherwise be analysed.

        Returns:
            Sequence[str]: Always an empty tuple of signature tokens.
        """

        del message
        return ()


class NullContextResolver(ContextResolver):
    """Implement a no-op context resolver."""

    def annotate(self, diagnostics: Iterable[Diagnostic], *, root: Path) -> None:
        """Ignore ``diagnostics`` leaving context unchanged.

        Args:
            diagnostics: Diagnostics to annotate (ignored).
            root: Project root for context resolution (ignored).
        """

        del diagnostics, root

    def resolve_context_for_lines(
        self,
        file_path: str,
        *,
        root: Path,
        lines: Iterable[int],
    ) -> dict[int, str]:
        """Return an empty context mapping for ``file_path``.

        Args:
            file_path: Path to the file being inspected (ignored).
            root: Project root directory (ignored).
            lines: Line numbers to resolve (ignored).

        Returns:
            dict[int, str]: Always an empty mapping.
        """

        del file_path, root, lines
        return {}


__all__ = ["NullAnnotationProvider", "NullContextResolver"]
