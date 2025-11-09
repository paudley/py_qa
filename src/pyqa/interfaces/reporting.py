# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Reporting interfaces (protocols only)."""

from __future__ import annotations

from abc import abstractmethod
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from pyqa.core.models import Diagnostic
from pyqa.core.severity import Severity
from pyqa.interfaces.core import JsonValue


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


@runtime_checkable
class ExitCategoryView(Protocol):
    """Lightweight projection of a tool exit category."""

    value: str
    """Machine-readable category identifier."""


@runtime_checkable
class DiagnosticView(Protocol):
    """View exposing diagnostic attributes to reporting layers."""

    file: str | None
    line: int | None
    column: int | None
    severity: Severity
    message: str
    tool: str
    code: str | None
    group: str | None
    hints: Sequence[str]
    tags: Sequence[str]
    meta: Mapping[str, JsonValue]


@runtime_checkable
class DiagnosticRecordView(Protocol):
    """View describing diagnostic records used for advice generation."""

    file_path: str | None
    line: int | None
    function: str | None
    tool: str
    code: str
    message: str


@runtime_checkable
class RawDiagnosticView(Protocol):
    """View representing raw tool diagnostics before normalisation."""

    file: str | None
    line: int | None
    column: int | None
    severity: Severity | str | None
    message: str
    code: str | None
    tool: str | None
    group: str | None


@runtime_checkable
class ToolOutcomeView(Protocol):
    """Projection of tool outcome data consumed by reporting and caching."""

    tool: str
    action: str
    returncode: int
    stdout: Sequence[str]
    stderr: Sequence[str]
    diagnostics: Sequence[DiagnosticView]
    cached: bool
    exit_category: ExitCategoryView


@runtime_checkable
class RunResultView(Protocol):
    """Projection of overall run results used across presentation layers."""

    root: Path
    files: Sequence[Path]
    outcomes: Sequence[ToolOutcomeView]


@runtime_checkable
class FileMetricsView(Protocol):
    """View describing per-file metrics persisted to caches."""

    line_count: int
    suppressions: Mapping[str, int]

    def to_payload(self) -> Mapping[str, JsonValue]:
        """Return a JSON-compatible mapping representing the metrics.

        Returns:
            Mapping[str, JsonValue]: Serialized metrics payload.
        """

        raise NotImplementedError

    @classmethod
    def from_payload(cls, payload: Mapping[str, JsonValue] | None) -> FileMetricsView:
        """Return a metrics instance constructed from ``payload``.

        Args:
            payload: Serialized metrics mapping or ``None`` when unavailable.

        Returns:
            FileMetricsView: Metrics reconstructed from ``payload``.
        """

        raise NotImplementedError


@dataclass(slots=True, frozen=True)
class DiagnosticRecord(DiagnosticRecordView):
    """Concrete diagnostic record shared across reporting components."""

    file_path: str | None
    line: int | None
    function: str | None
    tool: str
    code: str
    message: str


__all__ = [
    "AdviceProvider",
    "DiagnosticPresenter",
    "DiagnosticRecord",
    "DiagnosticRecordView",
    "DiagnosticView",
    "ExitCategoryView",
    "FileMetricsView",
    "RawDiagnosticView",
    "RunResultView",
    "ToolOutcomeView",
]
