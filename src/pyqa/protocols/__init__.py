# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Aggregate protocol definitions shared across the codebase.

The :mod:`pyqa.protocols` package hosts structural typing contracts that allow
components to depend on narrow interfaces instead of concrete implementations.
These modules intentionally avoid runtime dependencies on heavy subsystems so
they can be imported freely without triggering circular imports.
"""

from __future__ import annotations

from .cli import (
    CliCommand,
    CliCommandFactory,
    CliInvocation,
    CliParameterValue,
    CommandCallable,
    CommandDecorator,
    CommandRegistrationOptions,
    CommandResult,
    TyperLike,
    TyperSubApplication,
)
from .models import (
    DiagnosticRecordView,
    DiagnosticView,
    ExitCategoryView,
    FileMetricsView,
    RawDiagnosticView,
    RunResultView,
    ToolOutcomeView,
)
from .serialization import JsonScalar, JsonValue, SerializableMapping, SerializableValue, SupportsToDict

__all__ = [
    # CLI protocols -------------------------------------------------------------------------
    "CliCommand",
    "CliCommandFactory",
    "CliInvocation",
    "CliParameterValue",
    "CommandCallable",
    "CommandDecorator",
    "CommandRegistrationOptions",
    "CommandResult",
    "TyperSubApplication",
    "TyperLike",
    # Model projections ---------------------------------------------------------------------
    "DiagnosticRecordView",
    "DiagnosticView",
    "ExitCategoryView",
    "FileMetricsView",
    "RawDiagnosticView",
    "RunResultView",
    "ToolOutcomeView",
    # Serialization helpers -----------------------------------------------------------------
    "JsonScalar",
    "JsonValue",
    "SerializableMapping",
    "SerializableValue",
    "SupportsToDict",
]
