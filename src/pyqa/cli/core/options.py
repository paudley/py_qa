# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Data structures for lint command options."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final

from .lint_literals import (
    BanditLevelLiteral,
    OutputModeLiteral,
    PRSummarySeverityLiteral,
    SensitivityLiteral,
    StrictnessLiteral,
)


@dataclass(slots=True)
class LintTargetOptions:
    """File discovery parameters provided via CLI arguments."""

    root: Path
    paths: list[Path]
    dirs: list[Path]
    exclude: list[Path]
    paths_from_stdin: bool


@dataclass(slots=True)
class LintGitOptions:
    """Git discovery controls provided via CLI arguments."""

    changed_only: bool
    diff_ref: str
    include_untracked: bool
    base_branch: str | None
    no_lint_tests: bool


@dataclass(slots=True)
class LintSelectionOptions:
    """Tool selection filters derived from CLI arguments."""

    filters: list[str]
    only: list[str]
    language: list[str]
    fix_only: bool
    check_only: bool


@dataclass(slots=True)
class LintDisplayToggles:
    """Console display toggles shared between CLI and configuration layers."""

    verbose: bool
    quiet: bool
    no_color: bool
    no_emoji: bool
    output_mode: OutputModeLiteral


@dataclass(slots=True)
class LintDisplayOptions(LintDisplayToggles):
    """Display toggles extended with advice rendering support."""

    advice: bool


@dataclass(slots=True)
class LintSummaryOptions:
    """Summary rendering preferences supplied via CLI arguments."""

    show_passing: bool
    no_stats: bool
    pr_summary_out: Path | None
    pr_summary_limit: int
    pr_summary_min_severity: PRSummarySeverityLiteral
    pr_summary_template: str


@dataclass(slots=True)
class LintOutputBundle:
    """Bundle display and summary output preferences."""

    display: LintDisplayOptions
    summary: LintSummaryOptions


@dataclass(slots=True)
class ExecutionRuntimeOptions:
    """Execution runtime configuration shared across tools."""

    jobs: int | None
    bail: bool
    no_cache: bool
    cache_dir: Path
    use_local_linters: bool
    strict_config: bool


@dataclass(slots=True)
class ExecutionFormattingOptions:
    """Formatting overrides propagated to compatible tools."""

    line_length: int
    sql_dialect: str
    python_version: str | None


@dataclass(slots=True)
class LintExecutionOptions:
    """Execution runtime and formatting configuration for linting."""

    runtime: ExecutionRuntimeOptions
    formatting: ExecutionFormattingOptions


@dataclass(slots=True)
class LintComplexityOptions:
    """Complexity overrides shared across supported tools."""

    max_complexity: int | None
    max_arguments: int | None


@dataclass(slots=True)
class LintStrictnessOptions:
    """Type checking strictness override."""

    type_checking: StrictnessLiteral | None


@dataclass(slots=True)
class LintSeverityOptions:
    """Tool-specific severity overrides."""

    bandit_severity: BanditLevelLiteral | None
    bandit_confidence: BanditLevelLiteral | None
    pylint_fail_under: float | None
    sensitivity: SensitivityLiteral | None


@dataclass(slots=True)
class LintOverrideOptions:
    """Aggregated override bundles applied to downstream tooling."""

    complexity: LintComplexityOptions
    strictness: LintStrictnessOptions
    severity: LintSeverityOptions


@dataclass(slots=True)
class LintOptionBundles:
    """Aggregate component dataclasses required to build ``LintOptions``."""

    targets: LintTargetOptions
    git: LintGitOptions
    selection: LintSelectionOptions
    output: LintOutputBundle
    execution: LintExecutionOptions
    overrides: LintOverrideOptions


_OPTION_ATTRIBUTE_MAP: Final[dict[str, tuple[str, ...]]] = {
    "root": ("_targets", "root"),
    "paths": ("_targets", "paths"),
    "dirs": ("_targets", "dirs"),
    "exclude": ("_targets", "exclude"),
    "paths_from_stdin": ("_targets", "paths_from_stdin"),
    "changed_only": ("_git", "changed_only"),
    "diff_ref": ("_git", "diff_ref"),
    "include_untracked": ("_git", "include_untracked"),
    "base_branch": ("_git", "base_branch"),
    "no_lint_tests": ("_git", "no_lint_tests"),
    "filters": ("_selection", "filters"),
    "only": ("_selection", "only"),
    "language": ("_selection", "language"),
    "fix_only": ("_selection", "fix_only"),
    "check_only": ("_selection", "check_only"),
    "verbose": (
        "_output",
        "display",
        "verbose",
    ),
    "quiet": (
        "_output",
        "display",
        "quiet",
    ),
    "no_color": (
        "_output",
        "display",
        "no_color",
    ),
    "no_emoji": (
        "_output",
        "display",
        "no_emoji",
    ),
    "output_mode": (
        "_output",
        "display",
        "output_mode",
    ),
    "advice": (
        "_output",
        "display",
        "advice",
    ),
    "show_passing": (
        "_output",
        "summary",
        "show_passing",
    ),
    "no_stats": (
        "_output",
        "summary",
        "no_stats",
    ),
    "pr_summary_out": (
        "_output",
        "summary",
        "pr_summary_out",
    ),
    "pr_summary_limit": (
        "_output",
        "summary",
        "pr_summary_limit",
    ),
    "pr_summary_min_severity": (
        "_output",
        "summary",
        "pr_summary_min_severity",
    ),
    "pr_summary_template": (
        "_output",
        "summary",
        "pr_summary_template",
    ),
    "jobs": (
        "_execution",
        "runtime",
        "jobs",
    ),
    "bail": (
        "_execution",
        "runtime",
        "bail",
    ),
    "no_cache": (
        "_execution",
        "runtime",
        "no_cache",
    ),
    "cache_dir": (
        "_execution",
        "runtime",
        "cache_dir",
    ),
    "use_local_linters": (
        "_execution",
        "runtime",
        "use_local_linters",
    ),
    "strict_config": (
        "_execution",
        "runtime",
        "strict_config",
    ),
    "line_length": (
        "_execution",
        "formatting",
        "line_length",
    ),
    "sql_dialect": (
        "_execution",
        "formatting",
        "sql_dialect",
    ),
    "python_version": (
        "_execution",
        "formatting",
        "python_version",
    ),
    "max_complexity": (
        "_overrides",
        "complexity",
        "max_complexity",
    ),
    "max_arguments": (
        "_overrides",
        "complexity",
        "max_arguments",
    ),
    "type_checking": (
        "_overrides",
        "strictness",
        "type_checking",
    ),
    "bandit_severity": (
        "_overrides",
        "severity",
        "bandit_severity",
    ),
    "bandit_confidence": (
        "_overrides",
        "severity",
        "bandit_confidence",
    ),
    "pylint_fail_under": (
        "_overrides",
        "severity",
        "pylint_fail_under",
    ),
    "sensitivity": (
        "_overrides",
        "severity",
        "sensitivity",
    ),
}


class LintOptions:
    """Composite container for CLI-derived lint configuration."""

    __slots__ = (
        "_targets",
        "_git",
        "_selection",
        "_output",
        "_execution",
        "_overrides",
        "_provided",
    )

    if TYPE_CHECKING:
        root: Path
        cache_dir: Path
        paths: list[Path]
        dirs: list[Path]
        exclude: list[Path]
        paths_from_stdin: bool
        changed_only: bool
        diff_ref: str
        include_untracked: bool
        base_branch: str | None
        no_lint_tests: bool
        filters: list[str]
        only: list[str]
        language: list[str]
        fix_only: bool
        check_only: bool
        verbose: bool
        quiet: bool
        no_color: bool
        no_emoji: bool
        output_mode: OutputModeLiteral
        advice: bool
        show_passing: bool
        no_stats: bool
        pr_summary_out: Path | None
        pr_summary_limit: int
        pr_summary_min_severity: PRSummarySeverityLiteral
        pr_summary_template: str
        jobs: int | None
        bail: bool
        no_cache: bool
        use_local_linters: bool
        strict_config: bool
        line_length: int
        sql_dialect: str
        python_version: str | None
        max_complexity: int | None
        max_arguments: int | None
        type_checking: StrictnessLiteral | None
        bandit_severity: BanditLevelLiteral | None
        bandit_confidence: BanditLevelLiteral | None
        pylint_fail_under: float | None
        sensitivity: SensitivityLiteral | None

    def __init__(
        self,
        *,
        bundles: LintOptionBundles,
        provided: Iterable[str],
    ) -> None:
        """Initialise the composed lint options bundle.

        Args:
            bundles: Component dataclasses derived from CLI inputs.
            provided: Names of CLI flags that were explicitly provided by the user.

        """

        self._targets = bundles.targets
        self._git = bundles.git
        self._selection = bundles.selection
        self._output = bundles.output
        self._execution = bundles.execution
        self._overrides = bundles.overrides
        self._provided = frozenset(provided)

    @property
    def target_options(self) -> LintTargetOptions:
        """Return the CLI-provided target discovery options bundle.

        Returns:
            LintTargetOptions: Structured view of filesystem discovery inputs
            collected from the command line interface.
        """

        return self._targets

    @property
    def git_options(self) -> LintGitOptions:
        """Return the CLI git discovery options bundle.

        Returns:
            LintGitOptions: Aggregated git-discovery related inputs including
            revision boundaries and test skipping preferences.
        """

        return self._git

    @property
    def selection_options(self) -> LintSelectionOptions:
        """Return tool selection options derived from CLI arguments.

        Returns:
            LintSelectionOptions: Filters, language selection, and fix/check
            toggles used when building the execution plan.
        """

        return self._selection

    @property
    def output_bundle(self) -> LintOutputBundle:
        """Return the CLI output bundle containing display and summary data.

        Returns:
            LintOutputBundle: Nested display toggles and summary preferences
            gathered from the CLI invocation.
        """

        return self._output

    @property
    def execution_options(self) -> LintExecutionOptions:
        """Return the execution options bundle derived from CLI arguments.

        Returns:
            LintExecutionOptions: Runtime and formatting parameters scoped to
            downstream tool execution.
        """

        return self._execution

    @property
    def override_options(self) -> LintOverrideOptions:
        """Return the CLI override bundle for complexity and strictness.

        Returns:
            LintOverrideOptions: Aggregated overrides for complexity, typing,
            and severity enforcement passed via CLI flags.
        """

        return self._overrides

    def __getattr__(self, name: str) -> object:
        """Proxy attribute access to nested option bundles.

        Args:
            name: Attribute name requested by the caller.

        Returns:
            object: Value extracted from the composed lint option dataclasses.

        Raises:
            AttributeError: If ``name`` is not a recognised option attribute.

        """

        return self._resolve_attribute(name)

    def _resolve_attribute(self, name: str) -> object:
        """Return the nested attribute value associated with ``name``.

        Args:
            name: Attribute identifier defined in ``_OPTION_ATTRIBUTE_MAP``.

        Returns:
            object: Value obtained by traversing the configured attribute path.

        Raises:
            AttributeError: If the attribute name is not recognised.
        """

        path = _OPTION_ATTRIBUTE_MAP.get(name)
        if path is None:
            raise AttributeError(name) from None
        value: object = self
        for attribute in path:
            value = getattr(value, attribute)
        return value

    def __dir__(self) -> list[str]:
        """Return a merged attribute listing including proxied entries.

        Returns:
            list[str]: Combined attribute names exposed by the wrapper and
            nested dataclasses.

        """

        return sorted(set(super().__dir__()) | set(_OPTION_ATTRIBUTE_MAP))

    def __contains__(self, item: str) -> bool:
        """Return ``True`` when ``item`` was explicitly provided on the CLI.

        Args:
            item: CLI flag name to probe for explicit invocation.

        Returns:
            bool: ``True`` when ``item`` is recorded in ``provided``.

        """

        return item in self._provided

    def __repr__(self) -> str:
        """Return a deterministic representation for debugging support.

        Returns:
            str: Readable representation showing component dataclasses.

        """

        provided = sorted(self._provided)
        return (
            "LintOptions("
            f"targets={self._targets!r}, git={self._git!r}, selection={self._selection!r}, "
            f"output={self._output!r}, execution={self._execution!r}, "
            f"overrides={self._overrides!r}, provided={provided!r})"
        )

    @property
    def provided(self) -> frozenset[str]:
        """Return the set of CLI flags explicitly provided by the caller.

        Returns:
            frozenset[str]: Flag names supplied on the command line.

        """

        return self._provided


@dataclass(slots=True)
class InstallOptions:
    """Options controlling installation of managed tools."""

    include_optional: bool = True
    generate_stubs: bool = True


ToolFilters = dict[str, list[str]]
