# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Dataclasses capturing structured CLI inputs for the lint command."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TypeAlias

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
        """Return the toggles as a serialisable dictionary.

        Returns:
            dict[str, bool | OutputModeLiteral]: Mapping capturing current rendering settings.
        """

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
class RuntimeCoreChecks:
    """Toggle set for core runtime lint checks."""

    check_closures: bool
    check_signatures: bool
    check_cache_usage: bool
    check_value_types: bool
    check_value_types_general: bool


@dataclass(slots=True)
class RuntimeInterfaceChecks:
    """Toggle set for interface-driven runtime checks."""

    check_interfaces: bool
    check_di: bool
    check_module_docs: bool
    check_pyqa_python_hygiene: bool


@dataclass(slots=True)
class RuntimePolicyChecks:
    """Toggle set for compliance and hygiene-related runtime checks."""

    show_valid_suppressions: bool
    check_license_header: bool
    check_copyright: bool
    check_python_hygiene: bool


@dataclass(slots=True)
class RuntimeAdditionalChecks:
    """Toggle set for advanced runtime verifications."""

    check_file_size: bool
    check_schema_sync: bool
    pyqa_rules: bool


@dataclass(slots=True)
class MetaRuntimeChecks:
    """Aggregate runtime check toggles across core, interface, policy, and extras."""

    core: RuntimeCoreChecks
    interface: RuntimeInterfaceChecks
    policy: RuntimePolicyChecks
    additional: RuntimeAdditionalChecks


@dataclass(slots=True)
class LintMetaParams:
    """Aggregate meta toggles for lint command execution."""

    actions: MetaActionParams
    analysis: MetaAnalysisChecks
    runtime: MetaRuntimeChecks

    def __getattr__(self, attribute: str) -> MetaAttributeValue:
        """Proxy attribute access to underlying action and runtime groups.

        Args:
            attribute: Attribute name requested by callers expecting legacy fields.

        Returns:
            MetaAttributeValue: Value resolved from the aggregate structures.

        Raises:
            AttributeError: If ``attribute`` is not provided by any group.
            TypeError: If the resolved attribute is not a supported meta value type.
        """

        groups = (
            self.actions,
            self.analysis,
            self.runtime.core,
            self.runtime.interface,
            self.runtime.policy,
            self.runtime.additional,
        )
        for group in groups:
            if hasattr(group, attribute):
                value = getattr(group, attribute)
                if isinstance(value, (str, bool)) or value is None:
                    return value
                raise TypeError(
                    f"Meta attribute '{attribute}' has unsupported type {type(value)!r}; "
                    "expected bool, str, or None.",
                )
        raise AttributeError(attribute)


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


MetaAttributeValue: TypeAlias = bool | str | None


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
