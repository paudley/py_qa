# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Dataclasses capturing structured CLI inputs for the lint command."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar, Final, TypeAlias

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

RUNTIME_CORE_FLAGS: Final[tuple[str, ...]] = (
    "check_closures",
    "check_conditional_imports",
    "check_signatures",
    "check_cache_usage",
    "check_value_types",
    "check_value_types_general",
)
RUNTIME_INTERFACE_FLAGS: Final[tuple[str, ...]] = (
    "check_interfaces",
    "check_di",
    "check_module_docs",
    "check_pyqa_python_hygiene",
)
RUNTIME_POLICY_FLAGS: Final[tuple[str, ...]] = (
    "show_valid_suppressions",
    "check_license_header",
    "check_copyright",
    "check_python_hygiene",
)
RUNTIME_ADDITIONAL_FLAGS: Final[tuple[str, ...]] = (
    "check_file_size",
    "check_schema_sync",
    "pyqa_rules",
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
    explain_tools_json: str | None = None


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
    check_conditional_imports: bool
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
class RuntimeGroupOverrides:
    """Optional runtime check overrides grouped by enforcement tier."""

    core: RuntimeCoreChecks | None = None
    interface: RuntimeInterfaceChecks | None = None
    policy: RuntimePolicyChecks | None = None
    additional: RuntimeAdditionalChecks | None = None


RuntimeGroup = RuntimeCoreChecks | RuntimeInterfaceChecks | RuntimePolicyChecks | RuntimeAdditionalChecks


@dataclass(slots=True)
class RuntimeCoreFlagOverrides:
    """Boolean overrides for core runtime meta checks."""

    check_closures: bool = False
    check_conditional_imports: bool = False
    check_signatures: bool = False
    check_cache_usage: bool = False
    check_value_types: bool = False
    check_value_types_general: bool = False


@dataclass(slots=True)
class RuntimeInterfaceFlagOverrides:
    """Boolean overrides for interface runtime meta checks."""

    check_interfaces: bool = False
    check_di: bool = False
    check_module_docs: bool = False
    check_pyqa_python_hygiene: bool = False


@dataclass(slots=True)
class RuntimePolicyFlagOverrides:
    """Boolean overrides for policy runtime meta checks."""

    show_valid_suppressions: bool = False
    check_license_header: bool = False
    check_copyright: bool = False
    check_python_hygiene: bool = False


@dataclass(slots=True)
class RuntimeAdditionalFlagOverrides:
    """Boolean overrides for additional runtime meta checks."""

    check_file_size: bool = False
    check_schema_sync: bool = False
    pyqa_rules: bool = False


@dataclass(slots=True)
class RuntimeFlagOverrides:
    """Boolean overrides for runtime meta flags across all enforcement tiers."""

    core: RuntimeCoreFlagOverrides = field(default_factory=RuntimeCoreFlagOverrides)
    interface: RuntimeInterfaceFlagOverrides = field(default_factory=RuntimeInterfaceFlagOverrides)
    policy: RuntimePolicyFlagOverrides = field(default_factory=RuntimePolicyFlagOverrides)
    additional: RuntimeAdditionalFlagOverrides = field(default_factory=RuntimeAdditionalFlagOverrides)


@dataclass(slots=True, init=False)
class MetaRuntimeChecks:
    """Aggregate runtime check toggles across core, interface, policy, and extras."""

    core: RuntimeCoreChecks
    interface: RuntimeInterfaceChecks
    policy: RuntimePolicyChecks
    additional: RuntimeAdditionalChecks

    _CORE_FLAGS: ClassVar[tuple[str, ...]] = RUNTIME_CORE_FLAGS
    _INTERFACE_FLAGS: ClassVar[tuple[str, ...]] = RUNTIME_INTERFACE_FLAGS
    _POLICY_FLAGS: ClassVar[tuple[str, ...]] = RUNTIME_POLICY_FLAGS
    _ADDITIONAL_FLAGS: ClassVar[tuple[str, ...]] = RUNTIME_ADDITIONAL_FLAGS
    _ALL_FLAGS: ClassVar[tuple[str, ...]] = _CORE_FLAGS + _INTERFACE_FLAGS + _POLICY_FLAGS + _ADDITIONAL_FLAGS

    def __init__(
        self,
        *,
        overrides: RuntimeGroupOverrides | None = None,
        flags: RuntimeFlagOverrides | None = None,
    ) -> None:
        """Initialise runtime checks using grouped dataclasses or flat flags.

        Args:
            overrides: Optional runtime check overrides grouped by enforcement tiers.
            flags: Boolean overrides for the known runtime toggle set.
        """

        overrides = overrides or RuntimeGroupOverrides()
        flag_overrides = flags or RuntimeFlagOverrides()
        flag_values: dict[str, bool] = {name: bool(getattr(flag_overrides.core, name)) for name in self._CORE_FLAGS}
        flag_values.update({name: bool(getattr(flag_overrides.interface, name)) for name in self._INTERFACE_FLAGS})
        flag_values.update({name: bool(getattr(flag_overrides.policy, name)) for name in self._POLICY_FLAGS})
        flag_values.update({name: bool(getattr(flag_overrides.additional, name)) for name in self._ADDITIONAL_FLAGS})
        core_group = self._resolve_group(
            overrides.core,
            flag_values,
            self._CORE_FLAGS,
            RuntimeCoreChecks,
            group_name="core",
        )
        interface_group = self._resolve_group(
            overrides.interface,
            flag_values,
            self._INTERFACE_FLAGS,
            RuntimeInterfaceChecks,
            group_name="interface",
        )
        policy_group = self._resolve_group(
            overrides.policy,
            flag_values,
            self._POLICY_FLAGS,
            RuntimePolicyChecks,
            group_name="policy",
        )
        additional_group = self._resolve_group(
            overrides.additional,
            flag_values,
            self._ADDITIONAL_FLAGS,
            RuntimeAdditionalChecks,
            group_name="additional",
        )

        if flag_values:
            unexpected = ", ".join(sorted(flag_values))
            raise TypeError(f"Unexpected runtime meta flag(s): {unexpected}")

        object.__setattr__(self, "core", core_group)
        object.__setattr__(self, "interface", interface_group)
        object.__setattr__(self, "policy", policy_group)
        object.__setattr__(self, "additional", additional_group)

    @staticmethod
    def _resolve_group(
        group: RuntimeGroup | None,
        flags: dict[str, bool],
        flag_names: tuple[str, ...],
        factory: (
            type[RuntimeCoreChecks]
            | type[RuntimeInterfaceChecks]
            | type[RuntimePolicyChecks]
            | type[RuntimeAdditionalChecks]
        ),
        *,
        group_name: str,
    ) -> RuntimeGroup:
        """Resolve runtime overrides using explicit groups or boolean flags.

        Args:
            group: Optional pre-constructed runtime group override.
            flags: Mutable mapping of boolean flag values provided by callers.
            flag_names: Flag names associated with the runtime group.
            factory: Dataclass factory used to construct the runtime group.
            group_name: Human-readable name used in error messages.

        Returns:
            RuntimeCoreChecks | RuntimeInterfaceChecks | RuntimePolicyChecks | RuntimeAdditionalChecks:
            Instantiated runtime group populated from overrides or flags.

        Raises:
            TypeError: If explicit overrides and individual flags are supplied together.
        """

        if group is not None:
            for name in flag_names:
                flag_value = bool(flags.pop(name, False))
                if flag_value:
                    raise TypeError(
                        f"Runtime {group_name} group provided alongside '{name}'; "
                        "supply either grouped dataclasses or individual flags."
                    )
            return group

        values = {name: bool(flags.pop(name, False)) for name in flag_names}
        return factory(**values)


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
    "RUNTIME_CORE_FLAGS",
    "RUNTIME_INTERFACE_FLAGS",
    "RUNTIME_POLICY_FLAGS",
    "RUNTIME_ADDITIONAL_FLAGS",
    "MetaActionParams",
    "MetaAnalysisChecks",
    "MetaRuntimeChecks",
    "RuntimeGroupOverrides",
    "RuntimeCoreFlagOverrides",
    "RuntimeInterfaceFlagOverrides",
    "RuntimePolicyFlagOverrides",
    "RuntimeAdditionalFlagOverrides",
    "RuntimeFlagOverrides",
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
