"""Interfaces for diagnostics presentation and advice generation."""

from __future__ import annotations

from typing import Protocol, runtime_checkable
from collections.abc import Iterable


@runtime_checkable
class DiagnosticPresenter(Protocol):
    """Render diagnostics into a chosen output format."""

    def render(self, diagnostics: Iterable[object]) -> str:
        """Return the rendered representation for ``diagnostics``."""

        ...


@runtime_checkable
class AdviceProvider(Protocol):
    """Produce remediation advice for diagnostics."""

    def advise(self, diagnostics: Iterable[object]) -> Iterable[str]:
        """Return textual advice for the supplied diagnostics."""

        ...
