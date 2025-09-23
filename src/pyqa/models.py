# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Core data models shared across the pyqa package."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

from .severity import Severity


@dataclass(slots=True)
class OutputFilter:
    """A reusable regex filter applied to tool stdout/stderr."""

    patterns: Sequence[str] = ()
    _compiled: tuple[re.Pattern[str], ...] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._compiled = tuple(re.compile(p) for p in self.patterns)

    def apply(self, text: str) -> str:
        """Return *text* with lines matching any configured pattern removed."""

        if not text or not self._compiled:
            return text
        return "\n".join(
            line for line in text.splitlines() if not any(pattern.search(line) for pattern in self._compiled)
        )


# pylint: disable=too-many-instance-attributes
@dataclass(slots=True)
class Diagnostic:
    """Normalized lint diagnostic returned by tools."""

    file: str | None
    line: int | None
    column: int | None
    severity: Severity
    message: str
    tool: str
    code: str | None = None
    group: str | None = None
    function: str | None = None


# pylint: disable=too-many-instance-attributes
@dataclass(slots=True)
class RawDiagnostic:
    """Intermediate diagnostic that resembles tool-native structure."""

    file: str | None
    line: int | None
    column: int | None
    severity: Severity | str | None
    message: str
    code: str | None = None
    tool: str | None = None
    group: str | None = None
    function: str | None = None


@dataclass(slots=True)
class ToolOutcome:
    """Result bundle produced by each executed tool action."""

    tool: str
    action: str
    returncode: int
    stdout: str
    stderr: str
    diagnostics: list[Diagnostic] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Return ``True`` when the tool exited successfully."""

        return self.returncode == 0


@dataclass(slots=True)
class RunResult:
    """Aggregate result for a full orchestrator run."""

    root: Path
    files: list[Path]
    outcomes: list[ToolOutcome]
    tool_versions: dict[str, str] = field(default_factory=dict)

    @property
    def failed(self) -> bool:
        """Return ``True`` when any outcome failed."""

        return any(not outcome.ok for outcome in self.outcomes)
