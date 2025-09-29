# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Core data models shared across the pyqa package."""

from __future__ import annotations

import re
from pathlib import Path
from re import Pattern
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator, model_validator

from .metrics import FileMetrics
from .severity import Severity


class OutputFilter(BaseModel):
    """A reusable regex filter applied to tool stdout/stderr."""

    model_config = ConfigDict(frozen=True)

    patterns: tuple[str, ...] = Field(default_factory=tuple)
    _compiled: tuple[Pattern[str], ...] = PrivateAttr(default_factory=tuple)

    @model_validator(mode="after")
    def _compile_patterns(self) -> OutputFilter:
        """Compile the configured regex patterns for fast reuse."""
        self._compiled = tuple(re.compile(pattern) for pattern in self.patterns)
        return self

    def apply(self, text: str) -> str:
        """Return *text* with lines matching any configured pattern removed."""
        if not text or not self._compiled:
            return text
        return "\n".join(
            line for line in text.splitlines() if not any(pattern.search(line) for pattern in self._compiled)
        )


class Diagnostic(BaseModel):
    """Normalized lint diagnostic returned by tools."""

    model_config = ConfigDict(validate_assignment=True)

    file: str | None = None
    line: int | None = None
    column: int | None = None
    severity: Severity
    message: str
    tool: str
    code: str | None = None
    group: str | None = None
    function: str | None = None
    hints: tuple[str, ...] = Field(default_factory=tuple)
    tags: tuple[str, ...] = Field(default_factory=tuple)
    meta: dict[str, Any] = Field(default_factory=dict)


class RawDiagnostic(BaseModel):
    """Intermediate diagnostic that resembles tool-native structure."""

    model_config = ConfigDict(validate_assignment=True)

    file: str | None = None
    line: int | None = None
    column: int | None = None
    severity: Severity | str | None
    message: str
    code: str | None = None
    tool: str | None = None
    group: str | None = None
    function: str | None = None


class ToolOutcome(BaseModel):
    """Result bundle produced by each executed tool action."""

    model_config = ConfigDict(validate_assignment=True)

    tool: str
    action: str
    returncode: int
    stdout: list[str] = Field(default_factory=list)
    stderr: list[str] = Field(default_factory=list)
    diagnostics: list[Diagnostic] = Field(default_factory=list)

    @field_validator("stdout", "stderr", mode="before")
    @classmethod
    def _coerce_output(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        if isinstance(value, tuple):
            return [str(item) for item in value]
        if isinstance(value, str):
            return value.splitlines()
        return [str(value)]

    def is_ok(self) -> bool:
        """Return ``True`` when the tool exited successfully."""
        return self.returncode == 0

    @property
    def ok(self) -> bool:
        """Expose :meth:`is_ok` as an attribute-style accessor."""
        return self.is_ok()


class RunResult(BaseModel):
    """Aggregate result for a full orchestrator run."""

    model_config = ConfigDict(validate_assignment=True)

    root: Path
    files: list[Path]
    outcomes: list[ToolOutcome]
    tool_versions: dict[str, str] = Field(default_factory=dict)
    file_metrics: dict[str, FileMetrics] = Field(default_factory=dict)
    analysis: dict[str, Any] = Field(default_factory=dict)

    def has_failures(self) -> bool:
        """Return ``True`` when any outcome failed."""
        return any(not outcome.ok for outcome in self.outcomes)

    @property
    def failed(self) -> bool:
        """Expose :meth:`has_failures` as an attribute-style accessor."""
        return self.has_failures()
