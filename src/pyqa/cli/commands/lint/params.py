# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Dataclasses capturing structured CLI inputs for the lint command."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ...core.lint_literals import (
    BanditLevelLiteral,
    OutputModeLiteral,
    PRSummarySeverityLiteral,
    SensitivityLiteral,
    StrictnessLiteral,
)
from ...core.options import (
    ExecutionRuntimeOptions,
    LintDisplayToggles,
    LintGitOptions,
    LintSelectionOptions,
    LintSeverityOptions,
)


@dataclass(slots=True)
class LintPathParams:
    """Capture filesystem path arguments supplied to the CLI."""

    paths: list[Path]
    root: Path
    paths_from_stdin: bool
    dirs: list[Path]
    exclude: list[Path]
    include_dotfiles: bool


@dataclass(slots=True)
class LintPathToggles:
    """Capture toggle options that influence filesystem discovery."""

    paths_from_stdin: bool
    include_dotfiles: bool


LintGitParams = LintGitOptions
LintSelectionParams = LintSelectionOptions
LintExecutionRuntimeParams = ExecutionRuntimeOptions


@dataclass(slots=True)
class LintOutputParams(LintDisplayToggles):
    """Rendering preferences for user-facing output."""

    def as_dict(self) -> dict[str, bool | OutputModeLiteral]:
        """Return the toggles as a serialisable dictionary."""

        return {
            "verbose": self.verbose,
            "quiet": self.quiet,
            "no_color": self.no_color,
            "no_emoji": self.no_emoji,
            "debug": self.debug,
            "output_mode": self.output_mode,
        }

    def with_output_mode(self, output_mode: OutputModeLiteral) -> LintOutputParams:
        """Return a copy of the toggles with an updated output mode.

        Args:
            output_mode: Output mode literal requested by the caller.

        Returns:
            LintOutputParams: New instance reflecting the provided
            ``output_mode`` value.
        """

        return LintOutputParams(
            verbose=self.verbose,
            quiet=self.quiet,
            no_color=self.no_color,
            no_emoji=self.no_emoji,
            debug=self.debug,
            output_mode=output_mode,
        )


@dataclass(slots=True)
class LintReportingParams:
    """Reporting targets selected by the user."""

    show_passing: bool
    no_stats: bool
    report_json: Path | None
    sarif_out: Path | None
    pr_summary_out: Path | None


@dataclass(slots=True)
class LintSummaryParams:
    """Parameters controlling PR summary generation."""

    pr_summary_limit: int
    pr_summary_min_severity: PRSummarySeverityLiteral
    pr_summary_template: str
    advice: bool


@dataclass(slots=True)
class LintOverrideParams:
    """Shared override knobs applied to tool configurations."""

    line_length: int
    sql_dialect: str
    max_complexity: int | None
    max_arguments: int | None
    type_checking: StrictnessLiteral | None
    python_version: str | None


@dataclass(slots=True)
class LintSeverityParams(LintSeverityOptions):
    """Typed severity overrides returned by CLI dependencies."""

    def as_tuple(
        self,
    ) -> tuple[BanditLevelLiteral | None, BanditLevelLiteral | None, float | None, SensitivityLiteral | None]:
        """Return severity override values as a tuple.

        Returns:
            tuple[BanditLevelLiteral | None, BanditLevelLiteral | None, float | None, SensitivityLiteral | None]:
            Tuple capturing the severity overrides for Bandit, pylint, and
            sensitivity adjustments.
        """

        return (
            self.bandit_severity,
            self.bandit_confidence,
            self.pylint_fail_under,
            self.sensitivity,
        )


@dataclass(slots=True)
class MetaActionParams:
    """Capture command-level meta toggles that alter lint execution."""

    doctor: bool
    tool_info: str | None
    fetch_all_tools: bool
    validate_schema: bool
    normal: bool
    explain_tools: bool


@dataclass(slots=True)
class MetaAnalysisChecks:
    """Describe analysis-oriented meta check toggles."""

    check_docstrings: bool
    check_suppressions: bool
    check_types_strict: bool
    check_missing: bool


@dataclass(slots=True)
class MetaRuntimeChecks:
    """Capture runtime/tooling oriented meta check toggles."""

    check_closures: bool
    check_signatures: bool
    check_cache_usage: bool
    check_value_types: bool
    check_value_types_general: bool
    check_interfaces: bool
    check_di: bool
    check_module_docs: bool
    check_pyqa_python_hygiene: bool
    show_valid_suppressions: bool
    check_license_header: bool
    check_copyright: bool
    check_python_hygiene: bool
    check_file_size: bool
    check_schema_sync: bool
    pyqa_rules: bool


@dataclass(slots=True)
class LintMetaParams:
    """Aggregate meta toggles for lint command execution."""

    actions: MetaActionParams
    analysis: MetaAnalysisChecks
    runtime: MetaRuntimeChecks

    @property
    def doctor(self) -> bool:
        """Return whether the doctor meta action was requested."""

        return self.actions.doctor

    @property
    def tool_info(self) -> str | None:
        """Return the tool requested for ``--tool-info`` if provided."""

        return self.actions.tool_info

    @property
    def fetch_all_tools(self) -> bool:
        """Return whether tool prefetching was requested."""

        return self.actions.fetch_all_tools

    @property
    def validate_schema(self) -> bool:
        """Return whether catalog schema validation was requested."""

        return self.actions.validate_schema

    @property
    def normal(self) -> bool:
        """Return whether the normal preset flag was supplied."""

        return self.actions.normal

    @property
    def explain_tools(self) -> bool:
        """Return whether the explain-tools meta action was supplied."""

        return self.actions.explain_tools

    @property
    def check_docstrings(self) -> bool:
        """Return whether the internal docstring checker should run."""

        return self.analysis.check_docstrings

    @property
    def check_suppressions(self) -> bool:
        """Return whether lint suppression analysis should run."""

        return self.analysis.check_suppressions

    @property
    def check_types_strict(self) -> bool:
        """Return whether the strict typing checker should execute."""

        return self.analysis.check_types_strict

    @property
    def check_missing(self) -> bool:
        """Return whether the missing functionality checker should execute."""

        return self.analysis.check_missing

    @property
    def check_closures(self) -> bool:
        """Return whether closure usage analysis should run."""

        return self.runtime.check_closures

    @property
    def check_signatures(self) -> bool:
        """Return whether function signature analysis should execute."""

        return self.runtime.check_signatures

    @property
    def check_cache_usage(self) -> bool:
        """Return whether cache usage analysis should execute."""

        return self.runtime.check_cache_usage

    @property
    def check_value_types(self) -> bool:
        """Return whether value-type ergonomics should be validated."""

        return self.runtime.check_value_types

    @property
    def check_value_types_general(self) -> bool:
        """Return whether generic value-type guidance should execute."""

        return self.runtime.check_value_types_general

    @property
    def check_interfaces(self) -> bool:
        """Return whether interface enforcement should execute."""

        return self.runtime.check_interfaces

    @property
    def check_di(self) -> bool:
        """Return whether DI guardrails should execute."""

        return self.runtime.check_di

    @property
    def check_module_docs(self) -> bool:
        """Return whether module documentation verification should execute."""

        return self.runtime.check_module_docs

    @property
    def check_pyqa_python_hygiene(self) -> bool:
        """Return whether the pyqa-specific hygiene linter should run."""

        return self.runtime.check_pyqa_python_hygiene

    @property
    def show_valid_suppressions(self) -> bool:
        """Return whether validated suppressions should be surfaced."""

        return self.runtime.show_valid_suppressions

    @property
    def check_license_header(self) -> bool:
        """Return whether license header enforcement should run."""

        return self.runtime.check_license_header

    @property
    def check_copyright(self) -> bool:
        """Return whether copyright notice enforcement should run."""

        return self.runtime.check_copyright

    @property
    def check_python_hygiene(self) -> bool:
        """Return whether Python hygiene enforcement should run."""

        return self.runtime.check_python_hygiene

    @property
    def check_file_size(self) -> bool:
        """Return whether file size enforcement should run."""

        return self.runtime.check_file_size

    @property
    def check_schema_sync(self) -> bool:
        """Return whether schema documentation synchronisation should run."""

        return self.runtime.check_schema_sync

    @property
    def pyqa_rules(self) -> bool:
        """Return whether pyqa-scoped lint rules are enabled."""

        return self.runtime.pyqa_rules


@dataclass(slots=True)
class LintTargetGroup:
    """Group path discovery parameters with git selectors."""

    path: LintPathParams
    git: LintGitParams


@dataclass(slots=True)
class LintExecutionGroup:
    """Group tool selection and runtime execution options."""

    selection: LintSelectionParams
    runtime: LintExecutionRuntimeParams


@dataclass(slots=True)
class LintOutputGroup:
    """Combine rendering, reporting, and summary preferences."""

    rendering: LintOutputParams
    reporting: LintReportingParams
    summary: LintSummaryParams


@dataclass(slots=True)
class LintAdvancedGroup:
    """Aggregate advanced overrides and meta controls."""

    overrides: LintOverrideParams
    severity: LintSeverityParams
    meta: LintMetaParams


@dataclass(slots=True)
class LintCLIInputs:
    """Top-level container for structured CLI inputs."""

    targets: LintTargetGroup
    execution: LintExecutionGroup
    output: LintOutputGroup
    advanced: LintAdvancedGroup


@dataclass(slots=True)
class LintOutputArtifacts:
    """Filesystem artifacts generated by the lint command."""

    report_json: Path | None
    sarif_out: Path | None
    pr_summary_out: Path | None


@dataclass(slots=True)
class RuntimeConcurrencyParams:
    """CLI inputs related to parallelism and local linter usage."""

    jobs: int | None
    bail: bool
    use_local_linters: bool


@dataclass(slots=True)
class RuntimeCacheParams:
    """CLI inputs describing cache toggles and locations."""

    no_cache: bool
    cache_dir: Path


@dataclass(slots=True)
class OverrideFormattingParams:
    """Command-line inputs affecting formatting defaults."""

    line_length: int
    sql_dialect: str
    python_version: str | None


@dataclass(slots=True)
class OverrideThresholdParams:
    """Command-line thresholds for shared complexity limits."""

    max_complexity: int | None
    max_arguments: int | None


@dataclass(slots=True)
class OverrideStrictnessParams:
    """Command-line strictness overrides for type checking."""

    type_checking: StrictnessLiteral | None


__all__ = (
    "BanditLevelLiteral",
    "MetaActionParams",
    "MetaAnalysisChecks",
    "MetaRuntimeChecks",
    "LintAdvancedGroup",
    "LintCLIInputs",
    "LintExecutionGroup",
    "LintExecutionRuntimeParams",
    "LintGitParams",
    "LintMetaParams",
    "LintOutputArtifacts",
    "LintOutputGroup",
    "LintOutputParams",
    "LintOverrideParams",
    "LintPathParams",
    "LintPathToggles",
    "LintReportingParams",
    "LintSelectionParams",
    "LintSeverityParams",
    "LintSummaryParams",
    "LintTargetGroup",
    "OutputModeLiteral",
    "PRSummarySeverityLiteral",
    "RuntimeCacheParams",
    "RuntimeConcurrencyParams",
    "OverrideFormattingParams",
    "OverrideThresholdParams",
    "OverrideStrictnessParams",
    "SensitivityLiteral",
    "StrictnessLiteral",
)
