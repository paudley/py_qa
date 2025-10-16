# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Reporting interfaces (protocols only)."""

from __future__ import annotations

from abc import abstractmethod
from collections.abc import Iterable
from typing import Protocol, runtime_checkable

from pyqa.core.models import Diagnostic


@runtime_checkable
class DiagnosticPresenter(Protocol):
    """Render diagnostics into a chosen output format."""

    @property
    @abstractmethod
    def format_name(self) -> str:
        """Return the name of the format produced by the presenter.

        Returns:
            str: Identifier describing the rendered output format.
        """
        raise NotImplementedError

    @abstractmethod
    def render(self, diagnostics: Iterable[Diagnostic]) -> str:
        """Return rendered output for ``diagnostics``.

        Args:
            diagnostics: Iterable of diagnostics to present.

        Returns:
            str: Rendered representation of the diagnostics.
        """
        raise NotImplementedError


@runtime_checkable
class AdviceProvider(Protocol):
    """Produce remediation advice for diagnostics."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the identifier of the advice provider.

        Returns:
            str: Identifier describing the advice provider implementation.
        """
        raise NotImplementedError

    @abstractmethod
    def advise(self, diagnostics: Iterable[Diagnostic]) -> Iterable[str]:
        """Return textual advice for the supplied diagnostics.

        Args:
            diagnostics: Iterable of diagnostics requiring guidance.

        Returns:
            Iterable[str]: Advice strings for the provided diagnostics.
        """
        raise NotImplementedError


__all__ = ["AdviceProvider", "DiagnosticPresenter"]
