# SPDX-License-Identifier: MIT
"""Reporting interfaces (protocols only)."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol, runtime_checkable

from pyqa.core.models import Diagnostic


@runtime_checkable
class DiagnosticPresenter(Protocol):
    """Render diagnostics into a chosen output format."""

    @property
    def format_name(self) -> str:
        """Return the name of the format produced by the presenter."""
        raise NotImplementedError

    def render(self, diagnostics: Iterable[Diagnostic]) -> str:
        """Return rendered output for ``diagnostics``."""
        raise NotImplementedError


@runtime_checkable
class AdviceProvider(Protocol):
    """Produce remediation advice for diagnostics."""

    @property
    def provider_name(self) -> str:
        """Return the identifier of the advice provider."""
        raise NotImplementedError

    def advise(self, diagnostics: Iterable[Diagnostic]) -> Iterable[str]:
        """Return textual advice for the supplied diagnostics."""
        raise NotImplementedError


__all__ = ["AdviceProvider", "DiagnosticPresenter"]
