# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Shared quality-check data structures and protocols."""

from __future__ import annotations

from abc import abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from pyqa.interfaces.compliance import QualityConfigSection
from pyqa.interfaces.licensing import LicensePolicy


class QualityIssueLevel(str, Enum):
    """Define severity classifications for discovered quality issues."""

    ERROR = "error"
    WARNING = "warning"


class QualityIssue(BaseModel):
    """Capture a single issue discovered by a quality check."""

    model_config = ConfigDict(frozen=True)

    level: QualityIssueLevel
    message: str
    path: Path | None = None
    check: str | None = None


class QualityCheckResult(BaseModel):
    """Manage the quality issues collected during a run."""

    model_config = ConfigDict(validate_assignment=True)

    issues: list[QualityIssue] = Field(default_factory=list)

    def add_error(self, message: str, path: Path | None = None, *, check: str | None = None) -> None:
        """Record an error-level issue identified by a quality check.

        Args:
            message: Description of the issue.
            path: Optional file location associated with the issue.
            check: Optional identifier describing the originating check or sub-check.
        """

        issues = list(self.issues)
        issues.append(
            QualityIssue(
                level=QualityIssueLevel.ERROR,
                message=message,
                path=path,
                check=check,
            ),
        )
        self.issues = issues

    def add_warning(self, message: str, path: Path | None = None, *, check: str | None = None) -> None:
        """Record a warning-level issue identified by a quality check.

        Args:
            message: Description of the warning.
            path: Optional file location associated with the warning.
            check: Optional identifier describing the originating check or sub-check.
        """

        issues = list(self.issues)
        issues.append(
            QualityIssue(
                level=QualityIssueLevel.WARNING,
                message=message,
                path=path,
                check=check,
            ),
        )
        self.issues = issues

    @property
    def errors(self) -> list[QualityIssue]:
        """Return recorded issues that are classified as errors.

        Returns:
            list[QualityIssue]: Issues with severity ``ERROR``.
        """

        return [issue for issue in self.issues if issue.level is QualityIssueLevel.ERROR]

    @property
    def warnings(self) -> list[QualityIssue]:
        """Return recorded issues that are classified as warnings.

        Returns:
            list[QualityIssue]: Issues with severity ``WARNING``.
        """

        return [issue for issue in self.issues if issue.level is QualityIssueLevel.WARNING]

    def exit_code(self) -> int:
        """Calculate the process exit code implied by the collected issues.

        Returns:
            int: ``1`` when errors are present; otherwise ``0``.
        """

        return 1 if self.errors else 0


@dataclass(slots=True)
class QualityContext:
    """Shared context passed to individual quality checks."""

    root: Path
    files: Sequence[Path]
    quality: QualityConfigSection
    license_policy: LicensePolicy | None
    fix: bool = False


class QualityCheckProtocolError(RuntimeError):
    """Raised when a QualityCheck protocol method is invoked without an implementation."""


class QualityCheck(Protocol):
    """Define the contract for individual quality checks."""

    name: str

    @abstractmethod
    def run(self, ctx: QualityContext, result: QualityCheckResult) -> None:
        """Execute the check and append findings to ``result``.

        Args:
            ctx: Shared context describing the files and configuration.
            result: Accumulator capturing findings emitted by the check.

        Raises:
            QualityCheckProtocolError: Raised when an implementation does not override ``run``.
        """

        msg = "QualityCheck implementations must override run() to perform evaluations."
        raise QualityCheckProtocolError(msg)

    @abstractmethod
    def supports_fix(self) -> bool:
        """Indicate whether the check can perform in-place fixes.

        Returns:
            bool: ``True`` when automatic fixes are supported.

        Raises:
            QualityCheckProtocolError: Raised when an implementation does not override ``supports_fix``.
        """

        msg = "QualityCheck implementations must override supports_fix() to report fix capability."
        raise QualityCheckProtocolError(msg)


__all__ = [
    "QualityCheck",
    "QualityCheckResult",
    "QualityContext",
    "QualityIssue",
    "QualityIssueLevel",
]
