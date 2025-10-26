# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Protocols describing linting state shared across pyqa modules."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from pyqa.cli.commands.lint.cli_models import LintDisplayOptions as CLIDisplayOptions
from pyqa.cli.commands.lint.params import LintMetaParams, LintOutputArtifacts
from pyqa.cli.core.options import ExecutionFormattingOptions, LintOptions
from pyqa.cli.core.shared import CLILogger
from pyqa.interfaces.discovery import DiscoveryOptions

from .common import CacheControlOptions, RepositoryRootProvider


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
class LintRuntimeOptions(CacheControlOptions, Protocol):
    """Execution runtime switches relevant to internal linters."""

    __slots__ = ()


@runtime_checkable
class LintExecutionOptions(Protocol):
    """Execution option bundle made available to internal linters."""

    @property
    def runtime(self) -> LintRuntimeOptions:
        """Return runtime configuration derived from CLI inputs.

        Returns:
            LintRuntimeOptions: Runtime configuration for the lint run.
        """

        raise NotImplementedError

    @property
    def formatting(self) -> ExecutionFormattingOptions:
        """Return formatting overrides propagated to tooling.

        Returns:
            ExecutionFormattingOptions: Formatting configuration compatible with lint execution.
        """

        raise NotImplementedError


@runtime_checkable
class LintOptionsView(Protocol):
    """Composite lint options envelope exposed to internal linters."""

    @property
    def target_options(self) -> LintTargetOptions:
        """Return target discovery options for the active invocation.

        Returns:
            LintTargetOptions: Target discovery options used by the lint run.
        """

        raise NotImplementedError

    @property
    def execution_options(self) -> LintExecutionOptions:
        """Return execution configuration for the active invocation.

        Returns:
            LintExecutionOptions: Execution configuration used by the lint run.
        """

        raise NotImplementedError


@runtime_checkable
class PreparedLintState(RepositoryRootProvider, Protocol):
    """Minimal protocol describing the lint command state shared with linters."""

    @property
    def options(self) -> LintOptions | LintOptionsView:
        """Return the composed lint options prepared by the CLI layer.

        Returns:
            LintOptions | LintOptionsView: Lint option bundle applied to the run.
        """

        raise NotImplementedError

    @property
    def meta(self) -> LintMetaParams:
        """Return meta flags controlling optional lint behaviours.

        Returns:
            LintMetaParams: Meta parameters influencing lint execution.
        """

        raise NotImplementedError

    @property
    def ignored_py_qa(self) -> Sequence[str]:
        """Return paths that were ignored due to ``PY_QA`` directories.

        Returns:
            Sequence[str]: Ignored paths referencing ``PY_QA`` directories.
        """

        raise NotImplementedError

    @property
    def artifacts(self) -> LintOutputArtifacts:
        """Return filesystem artifacts requested for the lint run.

        Returns:
            LintOutputArtifacts: Requested lint output artifacts.
        """

        raise NotImplementedError

    @property
    def display(self) -> CLIDisplayOptions:
        """Return display options governing console output.

        Returns:
            CLIDisplayOptions: Display configuration for console output.
        """

        raise NotImplementedError

    @property
    def logger(self) -> CLILogger:
        """Return the CLI logger used to emit informational messages.

        Returns:
            CLILogger: Logger instance bound to the lint run.
        """

        raise NotImplementedError

    @property
    def suppressions(self) -> SuppressionRegistry | None:
        """Return the suppression registry when available.

        Returns:
            SuppressionRegistry | None: Suppression registry when configured.
        """

        raise NotImplementedError


__all__ = [
    "LintExecutionOptions",
    "LintOptionsView",
    "LintRuntimeOptions",
    "LintTargetOptions",
    "PreparedLintState",
    "SuppressionDirective",
    "SuppressionRegistry",
]
