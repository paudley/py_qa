# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Protocols describing linting state shared across pyqa modules."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from pyqa.cli.commands.lint.cli_models import LintDisplayOptions as CLIDisplayOptions
from pyqa.cli.commands.lint.params import LintMetaParams, LintOutputArtifacts
from pyqa.cli.core.options import LintOptions
from pyqa.cli.core.shared import CLILogger
from pyqa.interfaces.discovery import DiscoveryOptions

from .common import RepositoryRootProvider
from .tools import ExecutionOptions as ToolExecutionOptions
from .tools import RuntimeOptions as ToolRuntimeOptions


class SuppressionDirective(Protocol):
    """Protocol describing the metadata stored for an inline suppression directive."""

    @property
    def line(self) -> int:
        """Return the 1-based line number where the suppression appears.

        Returns:
            int: Line number associated with the suppression directive.
        """

        raise NotImplementedError

    @property
    def lints(self) -> Sequence[str]:
        """Return lint identifiers targeted by the suppression directive.

        Returns:
            Sequence[str]: Lint identifiers referenced by the directive.
        """

        raise NotImplementedError

    def lint_count(self) -> int:
        """Return the number of lint identifiers referenced by the directive.

        Returns:
            int: Count of lint identifiers captured by the directive.
        """

        return len(self.lints)


@runtime_checkable
class MissingFinding(Protocol):
    """Describe immutable attributes recorded for missing-code findings.

    Attributes:
        file: Path to the source file containing the finding.
        line: 1-based line number where the finding occurs.
        message: Human-readable description of the missing functionality.
        code: Diagnostic code associated with the missing finding.
    """

    @property
    def file(self) -> Path:
        """Return the source file containing the missing-code finding.

        Returns:
            Path: Source file path associated with the finding.
        """

        raise NotImplementedError

    @property
    def line(self) -> int:
        """Return the 1-based line number where the finding occurs.

        Returns:
            int: One-based line number for the finding.
        """

        raise NotImplementedError

    @property
    def message(self) -> str:
        """Return the human-readable description of the missing functionality.

        Returns:
            str: Human-readable diagnostic message.
        """

        raise NotImplementedError

    @property
    def code(self) -> str:
        """Return the diagnostic code associated with the missing finding.

        Returns:
            str: Diagnostic code describing the missing implementation.
        """

        raise NotImplementedError

    def location(self) -> tuple[Path, int]:
        """Return a tuple describing the file and line for the finding.

        Returns:
            tuple[Path, int]: Pair of (file path, 1-based line number).
        """

        return self.file, self.line


if TYPE_CHECKING:
    from pyqa.linting.suppressions import SuppressionRegistry
else:

    class SuppressionRegistry(Protocol):
        """Protocol describing suppression lookups required by internal linters."""

        def entries_for(self, path: Path) -> Sequence[SuppressionDirective]:
            """Return cached suppression directives for ``path``.

            Args:
                path: File whose suppressions should be loaded.

            Returns:
                Sequence[SuppressionDirective]: Cached suppression directives for ``path``.
            """

            raise NotImplementedError

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

            raise NotImplementedError


@runtime_checkable
class LintTargetOptions(DiscoveryOptions, Protocol):
    """Lint-specific wrapper around discovery options."""

    __slots__ = ()


@runtime_checkable
class LintRuntimeOptions(ToolRuntimeOptions, Protocol):
    """Execution runtime switches relevant to internal linters.

    Attributes:
        strict_config: Flag indicating whether strict configuration validation is enabled.
    """

    def is_strict_mode(self) -> bool:
        """Return ``True`` when strict configuration validation is active.

        Returns:
            bool: ``True`` when strict configuration validation is enabled.
        """

        return self.strict_config


@runtime_checkable
class LintExecutionOptions(ToolExecutionOptions, Protocol):
    """Execution option bundle made available to internal linters.

    Attributes:
        runtime: Runtime configuration derived from CLI inputs.
        formatting: Formatting overrides propagated to tooling.
    """

    def has_formatting_overrides(self) -> bool:
        """Return ``True`` when formatting overrides are present.

        Returns:
            bool: ``True`` if any formatting override fields are populated.
        """

        fmt = self.formatting
        return any(getattr(fmt, attr, None) for attr in ("line_length", "sql_dialect", "python_version"))


@runtime_checkable
class LintOptionsView(Protocol):
    """Composite lint options envelope exposed to internal linters.

    Attributes:
        target_options: Target discovery options for the active invocation.
        execution_options: Execution configuration for the active invocation.
    """

    @property
    def target_options(self) -> LintTargetOptions:
        """Return target discovery options for the active invocation.

        Returns:
            LintTargetOptions: Discovery options for the current run.
        """

        raise NotImplementedError

    @property
    def execution_options(self) -> LintExecutionOptions:
        """Return execution configuration for the active invocation.

        Returns:
            LintExecutionOptions: Execution configuration prepared for the run.
        """

        raise NotImplementedError

    def as_tuple(self) -> tuple[LintTargetOptions, LintExecutionOptions]:
        """Return the combined target and execution options.

        Returns:
            tuple[LintTargetOptions, LintExecutionOptions]: Paired view of options.
        """

        return (self.target_options, self.execution_options)


@runtime_checkable
class LintStateOptions(Protocol):
    """Expose option-level state shared with lint execution helpers."""

    @property
    def options(self) -> LintOptions | LintOptionsView:
        """Return the lint option bundle prepared by the CLI layer.

        Returns:
            LintOptions | LintOptionsView: Prepared lint option bundle.
        """

        raise NotImplementedError

    @property
    def meta(self) -> LintMetaParams:
        """Return meta flags controlling optional lint behaviours.

        Returns:
            LintMetaParams: Meta flags describing optional lint behaviours.
        """

        raise NotImplementedError

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
    """Expose artifact-level state shared across lint reporting helpers.

    Attributes:
        ignored_py_qa: Paths skipped due to ``PY_QA`` sentinel directories.
        artifacts: Filesystem artefacts requested for the lint run.
        display: Display options governing console output.
        logger: Logger instance bound to the lint run.
        suppressions: Optional suppression registry when configured.
    """

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
    "LintExecutionOptions",
    "LintOptionsView",
    "LintRuntimeOptions",
    "LintTargetOptions",
    "LintRunArtifacts",
    "LintStateOptions",
    "MissingFinding",
    "PreparedLintState",
    "SuppressionDirective",
    "SuppressionRegistry",
]
