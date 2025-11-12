# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""CLI option protocols shared with lint tooling."""

from __future__ import annotations

from abc import abstractmethod
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol, runtime_checkable

from ..discovery import DiscoveryOptions
from ..tools import (
    BanditLevelLiteral,
)
from ..tools import ExecutionOptions as ToolExecutionOptions
from ..tools import RuntimeOptions as ToolRuntimeOptions
from ..tools import (
    SensitivityLiteral,
    StrictnessLiteral,
)
from .logger import CLIDisplayOptions
from .types import LintOptionValue, PRSummarySeverityLiteral


@runtime_checkable
class LintGitOptionsView(Protocol):
    """Protocol describing git discovery overrides supplied via the CLI."""

    __slots__ = ()

    @property
    @abstractmethod
    def changed_only(self) -> bool:
        """Return ``True`` when only changed files should be linted.

        Returns:
            bool: ``True`` when only changed files should be linted.
        """

    @property
    @abstractmethod
    def diff_ref(self) -> str:
        """Return the diff reference used when selecting changed files.

        Returns:
            str: Diff reference used when selecting changed files.
        """

    @property
    @abstractmethod
    def include_untracked(self) -> bool:
        """Return ``True`` when untracked files should be included.

        Returns:
            bool: ``True`` when untracked files should be included.
        """

    @property
    @abstractmethod
    def base_branch(self) -> str | None:
        """Return the optional base branch used for diff calculations.

        Returns:
            str | None: Base branch used for diff calculations.
        """

    @property
    @abstractmethod
    def no_lint_tests(self) -> bool:
        """Return ``True`` when test files should be excluded.

        Returns:
            bool: ``True`` when test files should be excluded.
        """


@runtime_checkable
class LintSelectionOptionsView(Protocol):
    """Protocol describing tool selection overrides supplied via the CLI."""

    __slots__ = ()

    @property
    @abstractmethod
    def filters(self) -> Sequence[str]:
        """Return tool filter expressions applied to the lint run.

        Returns:
            Sequence[str]: Tool filter expressions applied to the run.
        """

    @property
    @abstractmethod
    def only(self) -> Sequence[str]:
        """Return explicit tool names requested by the user.

        Returns:
            Sequence[str]: Explicit tool names requested by the user.
        """

    @property
    @abstractmethod
    def language(self) -> Sequence[str]:
        """Return language filters applied to the lint run.

        Returns:
            Sequence[str]: Language filters applied to the run.
        """

    @property
    @abstractmethod
    def fix_only(self) -> bool:
        """Return ``True`` when only fix-capable tools should be executed.

        Returns:
            bool: ``True`` when only fix-capable tools should be executed.
        """

    @property
    @abstractmethod
    def check_only(self) -> bool:
        """Return ``True`` when only check-capable tools should be executed.

        Returns:
            bool: ``True`` when only check-capable tools should be executed.
        """


@runtime_checkable
class LintSummaryOptionsView(Protocol):
    """Protocol describing summary rendering preferences."""

    __slots__ = ()

    @property
    @abstractmethod
    def show_passing(self) -> bool:
        """Return ``True`` when passing diagnostics should be displayed.

        Returns:
            bool: ``True`` when passing diagnostics should be displayed.
        """

    @property
    @abstractmethod
    def no_stats(self) -> bool:
        """Return ``True`` when summary statistics should be suppressed.

        Returns:
            bool: ``True`` when summary statistics should be suppressed.
        """

    @property
    @abstractmethod
    def pr_summary_out(self) -> Path | None:
        """Return the optional path for PR summary output.

        Returns:
            Path | None: Path to the PR summary output file if configured.
        """

    @property
    @abstractmethod
    def pr_summary_limit(self) -> int:
        """Return the maximum number of findings included in summaries.

        Returns:
            int: Maximum number of findings included in summaries.
        """

    @property
    @abstractmethod
    def pr_summary_min_severity(self) -> PRSummarySeverityLiteral:
        """Return the minimum severity level included in summaries.

        Returns:
            PRSummarySeverityLiteral: Minimum severity level included in summaries.
        """

    @property
    @abstractmethod
    def pr_summary_template(self) -> str:
        """Return the template used for PR summary generation.

        Returns:
            str: Template used for PR summary generation.
        """


@runtime_checkable
class LintOutputBundleView(Protocol):
    """Protocol describing the composed output configuration bundle."""

    __slots__ = ()

    @property
    @abstractmethod
    def display(self) -> CLIDisplayOptions:
        """Return CLI display toggles applied to the lint run.

        Returns:
            CLIDisplayOptions: CLI display toggle bundle.
        """

    @property
    @abstractmethod
    def summary(self) -> LintSummaryOptionsView:
        """Return summary rendering preferences applied to the lint run.

        Returns:
            LintSummaryOptionsView: Summary rendering preferences.
        """


@runtime_checkable
class LintComplexityOptionsView(Protocol):
    """Protocol describing complexity override options."""

    __slots__ = ()

    @property
    @abstractmethod
    def max_complexity(self) -> int | None:
        """Return the optional maximum cyclomatic complexity.

        Returns:
            int | None: Maximum allowed cyclomatic complexity if constrained.
        """

    @property
    @abstractmethod
    def max_arguments(self) -> int | None:
        """Return the optional maximum argument count.

        Returns:
            int | None: Maximum allowed positional argument count if constrained.
        """


@runtime_checkable
class LintStrictnessOptionsView(Protocol):
    """Protocol describing strictness override options."""

    __slots__ = ()

    @property
    @abstractmethod
    def type_checking(self) -> StrictnessLiteral | None:
        """Return the optional type checking strictness override.

        Returns:
            StrictnessLiteral | None: Type checking strictness override when provided.
        """

    def has_override(self) -> bool:
        """Return ``True`` when a strictness override has been configured.

        Returns:
            bool: ``True`` when ``type_checking`` evaluates to a non-``None`` value.
        """

        return self.type_checking is not None


@runtime_checkable
class LintSeverityOptionsView(Protocol):
    """Protocol describing severity override options."""

    __slots__ = ()

    @property
    @abstractmethod
    def bandit_severity(self) -> BanditLevelLiteral | None:
        """Return the optional Bandit severity override.

        Returns:
            BanditLevelLiteral | None: Bandit severity override when provided.
        """

    @property
    @abstractmethod
    def bandit_confidence(self) -> BanditLevelLiteral | None:
        """Return the optional Bandit confidence override.

        Returns:
            BanditLevelLiteral | None: Bandit confidence override when provided.
        """

    @property
    @abstractmethod
    def pylint_fail_under(self) -> float | None:
        """Return the optional pylint score threshold.

        Returns:
            float | None: Minimum acceptable pylint score if constrained.
        """

    @property
    @abstractmethod
    def sensitivity(self) -> SensitivityLiteral | None:
        """Return the optional pyqa sensitivity override.

        Returns:
            SensitivityLiteral | None: Sensitivity override when configured.
        """


@runtime_checkable
class LintOverrideOptionsView(Protocol):
    """Protocol describing grouped override options for downstream tooling."""

    __slots__ = ()

    @property
    @abstractmethod
    def complexity(self) -> LintComplexityOptionsView:
        """Return complexity overrides applied to downstream tooling.

        Returns:
            LintComplexityOptionsView: Complexity override bundle provided by the user.
        """

    @property
    @abstractmethod
    def strictness(self) -> LintStrictnessOptionsView:
        """Return strictness overrides applied to downstream tooling.

        Returns:
            LintStrictnessOptionsView: Strictness override bundle provided by the user.
        """

    @property
    @abstractmethod
    def severity(self) -> LintSeverityOptionsView:
        """Return severity overrides applied to downstream tooling.

        Returns:
            LintSeverityOptionsView: Severity override bundle provided by the user.
        """


@runtime_checkable
class LintOptions(Protocol):
    """Protocol describing lint option payloads supplied by the CLI layer."""

    __slots__ = ()

    @property
    @abstractmethod
    def target_options(self) -> LintTargetOptions:
        """Return target discovery options for the lint run.

        Returns:
            LintTargetOptions: Discovery options associated with the lint run.
        """

    @property
    @abstractmethod
    def git_options(self) -> LintGitOptionsView:
        """Return git discovery options configured for the lint run.

        Returns:
            LintGitOptionsView: Git discovery options for the lint run.
        """

    @property
    @abstractmethod
    def selection_options(self) -> LintSelectionOptionsView:
        """Return tool selection options configured for the lint run.

        Returns:
            LintSelectionOptionsView: Tool selection options for the lint run.
        """

    @property
    @abstractmethod
    def output_bundle(self) -> LintOutputBundleView:
        """Return the output bundle governing reporting preferences.

        Returns:
            LintOutputBundleView: Output preferences for the lint run.
        """

    @property
    @abstractmethod
    def execution_options(self) -> LintExecutionOptions:
        """Return execution options for downstream tools.

        Returns:
            LintExecutionOptions: Execution options used by downstream tools.
        """

    @property
    @abstractmethod
    def override_options(self) -> LintOverrideOptionsView:
        """Return overrides applied to downstream tooling.

        Returns:
            LintOverrideOptionsView: Override bundle applied to downstream tooling.
        """

    @property
    @abstractmethod
    def provided(self) -> frozenset[str]:
        """Return the set of CLI flags explicitly provided by the user.

        Returns:
            frozenset[str]: CLI flags recorded as explicitly provided by the user.
        """

    @abstractmethod
    def __getattr__(self, name: str) -> LintOptionValue:
        """Return nested option values resolved by attribute name.

        Args:
            name: Attribute name to resolve within composed option bundles.

        Returns:
            LintOptionValue: Resolved option value.
        """

    @abstractmethod
    def __contains__(self, item: str) -> bool:
        """Return ``True`` when ``item`` was explicitly provided via the CLI.

        Args:
            item: Name of the CLI flag to test.

        Returns:
            bool: ``True`` when the flag was explicitly provided.
        """

    @abstractmethod
    def __dir__(self) -> list[str]:
        """Return the attribute names available on the composed options.

        Returns:
            list[str]: Attribute names exposed by the composed lint options.
        """

    @abstractmethod
    def with_added_provided(self, *flags: str) -> None:
        """Record additional CLI flags as explicitly provided.

        Args:
            *flags: Additional CLI flags to record as explicitly provided.
        """

    @abstractmethod
    def __repr__(self) -> str:
        """Return a deterministic representation helpful for debugging.

        Returns:
            str: Readable representation of the composed lint options.
        """


@runtime_checkable
class LintTargetOptions(DiscoveryOptions, Protocol):
    """Lint-specific wrapper around discovery options."""

    __slots__ = ()


@runtime_checkable
class LintRuntimeOptions(ToolRuntimeOptions, Protocol):
    """Execution runtime switches relevant to internal linters."""

    def is_strict_mode(self) -> bool:
        """Return ``True`` when strict configuration validation is active.

        Returns:
            bool: ``True`` when strict configuration validation is enabled.
        """

        return self.strict_config


@runtime_checkable
class LintExecutionOptions(ToolExecutionOptions, Protocol):
    """Execution option bundle made available to internal linters."""

    def has_formatting_overrides(self) -> bool:
        """Return ``True`` when formatting overrides are present.

        Returns:
            bool: ``True`` if any formatting override fields are populated.
        """

        fmt = self.formatting
        return any(getattr(fmt, attr, None) for attr in ("line_length", "sql_dialect", "python_version"))


@runtime_checkable
class LintOptionsView(Protocol):
    """Composite lint options envelope exposed to internal linters."""

    @property
    @abstractmethod
    def target_options(self) -> LintTargetOptions:
        """Return target discovery options for the active invocation.

        Returns:
            LintTargetOptions: Discovery options for the current run.
        """

    @property
    @abstractmethod
    def execution_options(self) -> LintExecutionOptions:
        """Return execution configuration for the active invocation.

        Returns:
            LintExecutionOptions: Execution configuration prepared for the run.
        """

    def as_tuple(self) -> tuple[LintTargetOptions, LintExecutionOptions]:
        """Return the combined target and execution options.

        Returns:
            tuple[LintTargetOptions, LintExecutionOptions]:
            Pair of (target options, execution options).
        """

        return (self.target_options, self.execution_options)


__all__ = [
    "LintComplexityOptionsView",
    "LintExecutionOptions",
    "LintGitOptionsView",
    "LintOptions",
    "LintOptionsView",
    "LintOutputBundleView",
    "LintOverrideOptionsView",
    "LintRuntimeOptions",
    "LintSelectionOptionsView",
    "LintSeverityOptionsView",
    "LintStrictnessOptionsView",
    "LintSummaryOptionsView",
    "LintTargetOptions",
]
