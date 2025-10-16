# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Licensing-related protocol definitions shared across compliance tooling."""

from __future__ import annotations

from abc import abstractmethod
from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class LicensePolicy(Protocol):
    """Expose essential operations required by the license fixer."""

    spdx_id: str | None
    allow_alternate_spdx: tuple[str, ...]
    require_spdx: bool
    require_notice: bool

    @abstractmethod
    def match_notice(self, content: str) -> str | None:
        """Return the matched copyright notice or ``None`` when missing.

        Args:
            content: File content inspected for the notice.

        Returns:
            str | None: Matched notice text when present; otherwise ``None``.
        """

    @abstractmethod
    def should_skip(self, path: Path, root: Path) -> bool:
        """Return ``True`` when ``path`` should be excluded from enforcement.

        Args:
            path: Candidate file path being evaluated.
            root: Repository root used for relative comparisons.

        Returns:
            bool: ``True`` when the file should be ignored.
        """


@runtime_checkable
class ExpectedNotice(Protocol):
    """Provide the canonical notice string for a file based on policy data."""

    @abstractmethod
    def __call__(
        self,
        policy: LicensePolicy,
        observed_notice: str | None,
        *,
        current_year: int | None = None,
    ) -> str | None:
        """Return the expected notice or ``None`` when none should be present.

        Args:
            policy: Active license policy driving evaluation.
            observed_notice: Notice detected in the current file content.
            current_year: Calendar year used for notice generation.

        Returns:
            str | None: Expected notice text, or ``None`` when no notice is required.
        """

    @abstractmethod
    def __repr__(self) -> str:
        """Return a developer-friendly representation of the callable.

        Returns:
            str: Informational description of the callable instance.
        """


@runtime_checkable
class ExtractSpdx(Protocol):
    """Provide SPDX identifier extraction from file content."""

    @abstractmethod
    def __call__(self, content: str) -> list[str]:
        """Identify SPDX identifiers in the provided content.

        Args:
            content: File content analysed for SPDX metadata.

        Returns:
            list[str]: Ordered SPDX identifiers discovered in the content.
        """

    @abstractmethod
    def __repr__(self) -> str:
        """Return a developer-friendly representation of the extractor.

        Returns:
            str: Informational description of the extractor instance.
        """


@runtime_checkable
class NormaliseNotice(Protocol):
    """Provide normalisation for copyright notice strings."""

    @abstractmethod
    def __call__(self, notice: str) -> str:
        """Normalise the representation of ``notice``.

        Args:
            notice: Original notice string requiring normalisation.

        Returns:
            str: Normalised notice string used for comparisons.
        """

    @abstractmethod
    def __repr__(self) -> str:
        """Return a developer-friendly representation of the normaliser.

        Returns:
            str: Informational description of the normaliser instance.
        """


__all__ = ["ExpectedNotice", "ExtractSpdx", "LicensePolicy", "NormaliseNotice"]
