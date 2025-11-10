# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Core data models shared across the pyqa package."""

from __future__ import annotations

import re
from collections.abc import Sequence
from enum import Enum
from pathlib import Path
from re import Pattern

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator, model_validator

from pyqa.core.metrics import FileMetrics
from pyqa.core.severity import Severity
from pyqa.filesystem.paths import normalize_path

type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]


class OutputFilter(BaseModel):
    """Apply reusable regex-based filters to tool stdout and stderr."""

    model_config = ConfigDict(frozen=True)

    patterns: tuple[str, ...] = Field(default_factory=tuple)
    _compiled: tuple[Pattern[str], ...] = PrivateAttr(default_factory=tuple)

    @model_validator(mode="after")
    def _compile_patterns(self) -> OutputFilter:
        """Compile the configured regex patterns for fast reuse.

        Returns:
            OutputFilter: Filter instance with compiled regex patterns cached.
        """

        self._compiled = tuple(re.compile(pattern) for pattern in self.patterns)
        return self

    def apply(self, text: str) -> str:
        """Remove lines in ``text`` that match configured patterns.

        Args:
            text: Raw output stream text to filter.

        Returns:
            str: Filtered output with matching lines removed.
        """

        if not text or not self._compiled:
            return text
        return "\n".join(
            line for line in text.splitlines() if not any(pattern.search(line) for pattern in self._compiled)
        )


class Diagnostic(BaseModel):
    """Standardize lint diagnostics returned by tools into a common schema."""

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
    meta: dict[str, JsonValue] = Field(default_factory=dict)


class RawDiagnostic(BaseModel):
    """Capture tool-native diagnostic structures prior to normalisation."""

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

    @field_validator("file", mode="before")
    @classmethod
    def _normalize_file(cls, value: str | Path | None) -> str | None:
        """Normalise diagnostic file paths relative to the invocation root.

        Args:
            value: Original file path emitted by the tool or ``None``.

        Returns:
            str | None: Normalised path string, or ``None`` when the tool omitted the value.
        """

        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return value
        raw = value if isinstance(value, Path) else Path(value)
        try:
            normalised = normalize_path(raw)
        except (OSError, RuntimeError, ValueError):
            return str(raw)
        return normalised.as_posix()


def coerce_output_sequence(value: JsonValue | Sequence[str] | None) -> list[str]:
    """Normalise stdout/stderr payloads into a list of strings.

    Args:
        value: Output payload supplied by a tool or serialized artifact.

    Returns:
        list[str]: Sequence of output lines represented as strings.
    """

    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, tuple):
        return [str(item) for item in value]
    if isinstance(value, str):
        return value.splitlines()
    return [str(value)]


class ToolExitCategory(str, Enum):
    """Enumerate high level categories for tool exit behaviour."""

    SUCCESS = "success"
    DIAGNOSTIC = "diagnostic"
    TOOL_FAILURE = "tool_failure"
    UNKNOWN = "unknown"


class ToolOutcome(BaseModel):
    """Capture the result bundle produced by each executed tool action.

    The :attr:`exit_category` field records the orchestrator's interpretation of
    the tool's exit status (success, diagnostic/code failure, or tool failure).
    Downstream code must rely on this category instead of the raw return code to
    differentiate operational failures from diagnostics surfaced by the tool.
    """

    model_config = ConfigDict(validate_assignment=True)

    tool: str
    action: str
    returncode: int
    stdout: list[str] = Field(default_factory=list)
    stderr: list[str] = Field(default_factory=list)
    diagnostics: list[Diagnostic] = Field(default_factory=list)
    cached: bool = False
    exit_category: ToolExitCategory = ToolExitCategory.UNKNOWN

    @field_validator("stdout", "stderr", mode="before")
    @classmethod
    def _coerce_output(cls, value: JsonValue | Sequence[str] | None) -> list[str]:
        """Normalise stdout/stderr payloads prior to model validation.

        Args:
            value: Raw output payload provided by the orchestrator.

        Returns:
            list[str]: Sequence of output lines represented as strings.
        """

        return coerce_output_sequence(value)

    def is_ok(self) -> bool:
        """Return whether the tool exited successfully.

        Returns:
            bool: ``True`` when the :attr:`returncode` equals ``0``.
        """
        return self.returncode == 0

    @property
    def ok(self) -> bool:
        """Expose :meth:`is_ok` as an attribute-style accessor.

        Returns:
            bool: ``True`` when the tool exited successfully.
        """
        return self.is_ok()

    def indicates_failure(self) -> bool:
        """Return whether the tool failed to execute successfully.

        Tools often emit diagnostics and exit with ``1`` to signal that issues
        were detected. Those runs are still considered *successful* from an
        operational standpoint because the tool completed its work. We only treat
        an action as failed when it exits in a way categorised as
        :class:`ToolExitCategory.TOOL_FAILURE` or when no diagnostics were
        produced and no explicit classification was provided, which typically
        indicates a crash, misconfiguration, or other runtime failure.

        Returns:
            bool: ``True`` when the outcome represents a runtime failure.
        """

        if self.exit_category == ToolExitCategory.TOOL_FAILURE:
            return True
        if self.exit_category in (ToolExitCategory.SUCCESS, ToolExitCategory.DIAGNOSTIC):
            return False
        return self.returncode != 0 and not self.diagnostics


class RunResult(BaseModel):
    """Aggregate results for a full orchestrator run."""

    model_config = ConfigDict(validate_assignment=True)

    root: Path
    files: list[Path]
    outcomes: list[ToolOutcome]
    tool_versions: dict[str, str] = Field(default_factory=dict)
    file_metrics: dict[str, FileMetrics] = Field(default_factory=dict)
    analysis: dict[str, JsonValue] = Field(default_factory=dict)

    def has_failures(self) -> bool:
        """Return whether any registered outcome failed.

        Returns:
            bool: ``True`` when at least one outcome signals failure.
        """
        return any(outcome.indicates_failure() for outcome in self.outcomes)

    def has_diagnostics(self) -> bool:
        """Return whether any tool emitted diagnostics.

        Returns:
            bool: ``True`` when at least one outcome captured diagnostics.
        """

        return any(outcome.diagnostics for outcome in self.outcomes)

    def diagnostic_count(self) -> int:
        """Return the total number of diagnostics emitted across all outcomes.

        Returns:
            int: Aggregate diagnostic count.
        """

        return sum(len(outcome.diagnostics) for outcome in self.outcomes)

    @property
    def failed(self) -> bool:
        """Expose :meth:`has_failures` as an attribute-style accessor.

        Returns:
            bool: ``True`` when any outcome signals failure.
        """
        return self.has_failures()
