# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Data structures for lint command options."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from ._lint_cli_models import (
    BanditLevelLiteral,
    OutputModeLiteral,
    PRSummarySeverityLiteral,
    SensitivityLiteral,
    StrictnessLiteral,
)


@dataclass(slots=True)
class LintTargetOptions:
    root: Path
    paths: list[Path]
    dirs: list[Path]
    exclude: list[Path]
    paths_from_stdin: bool


@dataclass(slots=True)
class LintGitOptions:
    changed_only: bool
    diff_ref: str
    include_untracked: bool
    base_branch: str | None
    no_lint_tests: bool


@dataclass(slots=True)
class LintSelectionOptions:
    filters: list[str]
    only: list[str]
    language: list[str]
    fix_only: bool
    check_only: bool


@dataclass(slots=True)
class LintDisplayOptions:
    verbose: bool
    quiet: bool
    no_color: bool
    no_emoji: bool
    output_mode: OutputModeLiteral
    advice: bool


@dataclass(slots=True)
class LintSummaryOptions:
    show_passing: bool
    no_stats: bool
    pr_summary_out: Path | None
    pr_summary_limit: int
    pr_summary_min_severity: PRSummarySeverityLiteral
    pr_summary_template: str


@dataclass(slots=True)
class LintOutputBundle:
    display: LintDisplayOptions
    summary: LintSummaryOptions


@dataclass(slots=True)
class ExecutionRuntimeOptions:
    jobs: int | None
    bail: bool
    no_cache: bool
    cache_dir: Path
    use_local_linters: bool
    strict_config: bool


@dataclass(slots=True)
class ExecutionFormattingOptions:
    line_length: int
    sql_dialect: str
    python_version: str | None


@dataclass(slots=True)
class LintExecutionOptions:
    runtime: ExecutionRuntimeOptions
    formatting: ExecutionFormattingOptions


@dataclass(slots=True)
class LintComplexityOptions:
    max_complexity: int | None
    max_arguments: int | None


@dataclass(slots=True)
class LintStrictnessOptions:
    type_checking: StrictnessLiteral | None


@dataclass(slots=True)
class LintSeverityOptions:
    bandit_severity: BanditLevelLiteral | None
    bandit_confidence: BanditLevelLiteral | None
    pylint_fail_under: float | None
    sensitivity: SensitivityLiteral | None


@dataclass(slots=True)
class LintOverrideOptions:
    complexity: LintComplexityOptions
    strictness: LintStrictnessOptions
    severity: LintSeverityOptions


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

    def __init__(
        self,
        *,
        targets: LintTargetOptions,
        git: LintGitOptions,
        selection: LintSelectionOptions,
        output: LintOutputBundle,
        execution: LintExecutionOptions,
        overrides: LintOverrideOptions,
        provided: Iterable[str],
    ) -> None:
        self._targets = targets
        self._git = git
        self._selection = selection
        self._output = output
        self._execution = execution
        self._overrides = overrides
        self._provided = set(provided)

    # File discovery -----------------------------------------------------------------

    @property
    def root(self) -> Path:
        return self._targets.root

    @property
    def paths(self) -> list[Path]:
        return self._targets.paths

    @property
    def dirs(self) -> list[Path]:
        return self._targets.dirs

    @property
    def exclude(self) -> list[Path]:
        return self._targets.exclude

    @property
    def paths_from_stdin(self) -> bool:
        return self._targets.paths_from_stdin

    # Git discovery ------------------------------------------------------------------

    @property
    def changed_only(self) -> bool:
        return self._git.changed_only

    @property
    def diff_ref(self) -> str:
        return self._git.diff_ref

    @property
    def include_untracked(self) -> bool:
        return self._git.include_untracked

    @property
    def base_branch(self) -> str | None:
        return self._git.base_branch

    @property
    def no_lint_tests(self) -> bool:
        return self._git.no_lint_tests

    # Selection ----------------------------------------------------------------------

    @property
    def filters(self) -> list[str]:
        return self._selection.filters

    @property
    def only(self) -> list[str]:
        return self._selection.only

    @property
    def language(self) -> list[str]:
        return self._selection.language

    @property
    def fix_only(self) -> bool:
        return self._selection.fix_only

    @property
    def check_only(self) -> bool:
        return self._selection.check_only

    # Output -------------------------------------------------------------------------

    @property
    def verbose(self) -> bool:
        return self._output.display.verbose

    @property
    def quiet(self) -> bool:
        return self._output.display.quiet

    @property
    def no_color(self) -> bool:
        return self._output.display.no_color

    @property
    def no_emoji(self) -> bool:
        return self._output.display.no_emoji

    @property
    def output_mode(self) -> str:
        return self._output.display.output_mode

    @property
    def advice(self) -> bool:
        return self._output.display.advice

    @property
    def show_passing(self) -> bool:
        return self._output.summary.show_passing

    @property
    def no_stats(self) -> bool:
        return self._output.summary.no_stats

    @property
    def pr_summary_out(self) -> Path | None:
        return self._output.summary.pr_summary_out

    @property
    def pr_summary_limit(self) -> int:
        return self._output.summary.pr_summary_limit

    @property
    def pr_summary_min_severity(self) -> str:
        return self._output.summary.pr_summary_min_severity

    @property
    def pr_summary_template(self) -> str:
        return self._output.summary.pr_summary_template

    # Execution ----------------------------------------------------------------------

    @property
    def jobs(self) -> int | None:
        return self._execution.runtime.jobs

    @property
    def bail(self) -> bool:
        return self._execution.runtime.bail

    @property
    def no_cache(self) -> bool:
        return self._execution.runtime.no_cache

    @property
    def cache_dir(self) -> Path:
        return self._execution.runtime.cache_dir

    @property
    def use_local_linters(self) -> bool:
        return self._execution.runtime.use_local_linters

    @property
    def strict_config(self) -> bool:
        return self._execution.runtime.strict_config

    @property
    def line_length(self) -> int:
        return self._execution.formatting.line_length

    @property
    def sql_dialect(self) -> str:
        return self._execution.formatting.sql_dialect

    @property
    def python_version(self) -> str | None:
        return self._execution.formatting.python_version

    # Overrides ----------------------------------------------------------------------

    @property
    def max_complexity(self) -> int | None:
        return self._overrides.complexity.max_complexity

    @property
    def max_arguments(self) -> int | None:
        return self._overrides.complexity.max_arguments

    @property
    def type_checking(self) -> str | None:
        return self._overrides.strictness.type_checking

    @property
    def bandit_severity(self) -> str | None:
        return self._overrides.severity.bandit_severity

    @property
    def bandit_confidence(self) -> str | None:
        return self._overrides.severity.bandit_confidence

    @property
    def pylint_fail_under(self) -> float | None:
        return self._overrides.severity.pylint_fail_under

    @property
    def sensitivity(self) -> str | None:
        return self._overrides.severity.sensitivity

    # Provided flags -----------------------------------------------------------------

    @property
    def provided(self) -> set[str]:
        return self._provided


@dataclass(slots=True)
class InstallOptions:
    """Options controlling installation of managed tools."""

    include_optional: bool = True
    generate_stubs: bool = True


ToolFilters = dict[str, list[str]]
