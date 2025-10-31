# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Protocols describing model projections shared between modules."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Protocol, runtime_checkable

from pyqa.core.severity import Severity

from .serialization import JsonValue


@runtime_checkable
class ExitCategoryView(Protocol):
    """Lightweight projection of :class:`pyqa.core.models.ToolExitCategory`."""

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
        """Return a JSON-compatible mapping representing the metrics."""

        ...

    @classmethod
    def from_payload(cls, payload: Mapping[str, JsonValue] | None) -> FileMetricsView:
        """Instantiate metrics from the serialised representation."""

        ...
