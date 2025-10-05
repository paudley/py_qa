# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Interfaces for diagnostics presentation and advice generation."""

# pylint: disable=too-few-public-methods

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol, runtime_checkable


@runtime_checkable
class DiagnosticPresenter(Protocol):
    """Render diagnostics into a chosen output format."""

    def render(self, diagnostics: Iterable[object]) -> str:
        """Return the rendered representation for ``diagnostics``."""
        raise NotImplementedError


@runtime_checkable
class AdviceProvider(Protocol):
    """Produce remediation advice for diagnostics."""

    def advise(self, diagnostics: Iterable[object]) -> Iterable[str]:
        """Return textual advice for the supplied diagnostics."""
        raise NotImplementedError
