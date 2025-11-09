# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Runtime state protocols shared with linting helpers."""

from __future__ import annotations

from abc import abstractmethod
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol, runtime_checkable

from ..common import RepositoryRootProvider
from .logger import CLIDisplayOptions, CLILogger
from .meta import LintMetaParams
from .options import LintOptions, LintOptionsView


@runtime_checkable
class LintOutputArtifacts(Protocol):
    """Protocol describing filesystem artefacts produced by lint operations."""

    __slots__ = ()

    @property
    def report_json(self) -> Path | None:
        """Return the optional path storing JSON report output.

        Returns:
            Path | None: Path to the JSON report file when configured.
        """

    @property
    def sarif_out(self) -> Path | None:
        """Return the optional path storing SARIF output.

        Returns:
            Path | None: Path to the SARIF output file when configured.
        """

    @property
    def pr_summary_out(self) -> Path | None:
        """Return the optional path storing PR summary output.

        Returns:
            Path | None: Path to the PR summary file when configured.
        """

    def as_tuple(self) -> tuple[Path | None, Path | None, Path | None]:
        """Return the artefact paths as a tuple ordered by creation priority.

        Returns:
            tuple[Path | None, Path | None, Path | None]: Tuple of artefact paths.
        """

        return (self.report_json, self.sarif_out, self.pr_summary_out)


class SuppressionDirective(Protocol):
    """Protocol describing the metadata stored for an inline suppression directive."""

    @property
    @abstractmethod
    def line(self) -> int:
        """Return the 1-based line number where the suppression appears.

        Returns:
            int: Line number associated with the suppression directive.
        """

    @property
    @abstractmethod
    def lints(self) -> Sequence[str]:
        """Return lint identifiers targeted by the suppression directive.

        Returns:
            Sequence[str]: Lint identifiers referenced by the directive.
        """

    def lint_count(self) -> int:
        """Return the number of lint identifiers referenced by the directive.

        Returns:
            int: Count of lint identifiers captured by the directive.
        """

        return len(self.lints)


@runtime_checkable
class MissingFinding(Protocol):
    """Describe immutable attributes recorded for missing-code findings."""

    @property
    @abstractmethod
    def file(self) -> Path:
        """Return the source file containing the missing-code finding.

        Returns:
            Path: Source file path associated with the finding.
        """

    @property
    @abstractmethod
    def line(self) -> int:
        """Return the 1-based line number where the finding occurs.

        Returns:
            int: One-based line number for the finding.
        """

    @property
    @abstractmethod
    def message(self) -> str:
        """Return the human-readable description of the missing functionality.

        Returns:
            str: Human-readable diagnostic message.
        """

    @property
    @abstractmethod
    def code(self) -> str:
        """Return the diagnostic code associated with the missing finding.

        Returns:
            str: Diagnostic code describing the missing implementation.
        """

    def location(self) -> tuple[Path, int]:
        """Return a tuple describing the file and line for the finding.

        Returns:
            tuple[Path, int]: Pair of (file path, 1-based line number).
        """

        return self.file, self.line


class SuppressionRegistry(Protocol):
    """Protocol describing suppression lookups required by internal linters."""

    @abstractmethod
    def entries_for(self, path: Path) -> Sequence[SuppressionDirective]:
        """Return cached suppression directives for ``path``.

        Args:
            path: File whose suppressions should be loaded.

        Returns:
            Sequence[SuppressionDirective]: Cached suppression directives for ``path``.
        """

    @abstractmethod
    def should_suppress(self, path: Path, line: int, *, tool: str, code: str) -> bool:
        """Return ``True`` when the specified diagnostic should be suppressed.

        Args:
            path: File containing the diagnostic.
            line: 1-based line number of the diagnostic.
            tool: Tool identifier associated with the diagnostic.
            code: Diagnostic code emitted by the tool.

        Returns:
            bool: ``True`` when the diagnostic should be suppressed.
        """


@runtime_checkable
class LintStateOptions(Protocol):
    """Expose option-level state shared with lint execution helpers."""

    @property
    @abstractmethod
    def options(self) -> LintOptions | LintOptionsView:
        """Return the lint option bundle prepared by the CLI layer.

        Returns:
            LintOptions | LintOptionsView: Prepared lint option bundle.
        """

    @property
    @abstractmethod
    def meta(self) -> LintMetaParams:
        """Return meta flags controlling optional lint behaviours.

        Returns:
            LintMetaParams: Meta flags describing optional lint behaviours.
        """

    def has_meta_flag(self, flag: str) -> bool:
        """Return ``True`` when ``flag`` is present on the meta options.

        Args:
            flag: Name of the meta attribute to query.

        Returns:
            bool: ``True`` when the corresponding meta attribute evaluates truthy.
        """

        return bool(getattr(self.meta, flag, False))


@runtime_checkable
class LintRunArtifacts(Protocol):
    """Expose artifact-level state shared across lint reporting helpers."""

    ignored_py_qa: Sequence[str]
    artifacts: LintOutputArtifacts
    display: CLIDisplayOptions
    logger: CLILogger
    suppressions: SuppressionRegistry | None

    def iter_ignored_py_qa(self) -> Sequence[str]:
        """Return a tuple view of ``PY_QA`` entries skipped by the run.

        Returns:
            Sequence[str]: Tuple containing ignored ``PY_QA`` directory paths.
        """

        return tuple(self.ignored_py_qa)

    def has_suppressions(self) -> bool:
        """Return ``True`` when a suppression registry has been configured.

        Returns:
            bool: ``True`` if a suppression registry instance is present.
        """

        return self.suppressions is not None


@runtime_checkable
class PreparedLintState(RepositoryRootProvider, LintStateOptions, LintRunArtifacts, Protocol):
    """Minimal protocol describing the lint command state shared with linters."""

    __slots__ = ()


__all__ = [
    "LintOutputArtifacts",
    "LintRunArtifacts",
    "LintStateOptions",
    "MissingFinding",
    "PreparedLintState",
    "SuppressionDirective",
    "SuppressionRegistry",
]
