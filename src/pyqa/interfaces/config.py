# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Configuration loading and mutation interfaces."""

from __future__ import annotations

from abc import abstractmethod
from collections.abc import Collection, Mapping, Sequence
from pathlib import Path
from typing import Literal, Protocol, Self, TypeAlias, cast, runtime_checkable

from pyqa.config.models.sections.clean import CleanConfig
from pyqa.config.models.sections.dedupe import DedupeConfig
from pyqa.config.models.sections.update import UpdateConfig
from pyqa.config.types import ConfigFragment, ConfigValue, MutableConfigFragment
from pyqa.interfaces.compliance import LicenseConfig
from pyqa.interfaces.discovery import FileDiscoveryConfig

SharedKnobValue: TypeAlias = ConfigValue | str
SensitivityLevelLiteral: TypeAlias = Literal["low", "medium", "high", "maximum"]


@runtime_checkable
class SharedKnobSnapshot(Protocol):
    """Describe baseline shared configuration knob values."""

    @property
    def knob_values(self) -> Mapping[str, SharedKnobValue]:
        """Return the raw mapping of knob values.

        Returns:
            Mapping[str, SharedKnobValue]: The raw mapping of knob values.
        """
        return cast(Mapping[str, SharedKnobValue], NotImplemented)

    def value_for(self, tool: str, key: str) -> SharedKnobValue:
        """Return the baseline value stored for ``tool`` and ``key``.

        Args:
            tool: Tool identifier requesting the baseline value.
            key: Tool setting requested by the caller.

        Returns:
            SharedKnobValue: Baseline knob value for the setting.
        """
        return cast(SharedKnobValue, NotImplemented)


OutputModeLiteral: TypeAlias = Literal["pretty", "raw", "concise"]
PrettyFormatLiteral: TypeAlias = Literal["text", "jsonl", "markdown"]
ReportFormatLiteral: TypeAlias = Literal["json"]
PrSummarySeverityLiteral: TypeAlias = Literal["error", "warning", "notice", "note"]


class OutputDisplayOptions(Protocol):
    """Console display options controlling how diagnostics are rendered."""

    @property
    def verbose(self) -> bool:
        """Return whether verbose output is requested.

        Returns:
            bool: ``True`` when verbose output should be produced.
        """

        return cast(bool, NotImplemented)

    @property
    def emoji(self) -> bool:
        """Return whether emoji output can be rendered.

        Returns:
            bool: ``True`` when emoji rendering is permitted.
        """

        return cast(bool, NotImplemented)

    @property
    def color(self) -> bool:
        """Return whether coloured output is enabled.

        Returns:
            bool: ``True`` when colourful output should be produced.
        """

        return cast(bool, NotImplemented)

    @property
    def show_passing(self) -> bool:
        """Return whether passing tool outcomes should be displayed.

        Returns:
            bool: ``True`` when passing outcomes should be included.
        """

        return cast(bool, NotImplemented)

    @property
    def show_stats(self) -> bool:
        """Return whether the statistics panel should be rendered.

        Returns:
            bool: ``True`` when run statistics should be displayed.
        """

        return cast(bool, NotImplemented)

    @property
    def output(self) -> OutputModeLiteral:
        """Return the selected output mode.

        Returns:
            OutputModeLiteral: Output mode identifier such as ``\"pretty\"``.
        """

        return cast(OutputModeLiteral, NotImplemented)

    @property
    def pretty_format(self) -> PrettyFormatLiteral:
        """Return the rendering format used for pretty output mode.

        Returns:
            PrettyFormatLiteral: Pretty renderer format identifier.
        """

        return cast(PrettyFormatLiteral, NotImplemented)

    @property
    def group_by_code(self) -> bool:
        """Return whether diagnostics should be grouped by code in reports.

        Returns:
            bool: ``True`` when diagnostics should be grouped by code.
        """

        return cast(bool, NotImplemented)

    @property
    def quiet(self) -> bool:
        """Return whether quiet mode suppresses most output.

        Returns:
            bool: ``True`` when quiet output is requested.
        """

        return cast(bool, NotImplemented)

    @property
    def tool_filters(self) -> dict[str, list[str]]:
        """Return the per-tool filter configuration.

        Returns:
            dict[str, list[str]]: Per-tool filter configuration.
        """

        return cast(dict[str, list[str]], NotImplemented)

    @property
    def advice(self) -> bool:
        """Return whether advice panels should be rendered.

        Returns:
            bool: ``True`` when advice generation is enabled.
        """

        return cast(bool, NotImplemented)


class OutputArtifactOptions(Protocol):
    """Artifact configuration controlling exported reports and annotations."""

    @property
    def report(self) -> ReportFormatLiteral | None:
        """Return the report format requested by the user.

        Returns:
            ReportFormatLiteral | None: Report format identifier or ``None``.
        """

        return cast(ReportFormatLiteral | None, NotImplemented)

    @property
    def report_out(self) -> Path | None:
        """Return the path where report artifacts should be written.

        Returns:
            Path | None: Output path for reports or ``None`` when disabled.
        """

        return cast(Path | None, NotImplemented)

    @property
    def report_include_raw(self) -> bool:
        """Return whether raw diagnostics should be embedded in reports.

        Returns:
            bool: ``True`` when raw diagnostics should be included.
        """

        return cast(bool, NotImplemented)

    @property
    def sarif_out(self) -> Path | None:
        """Return the SARIF output path.

        Returns:
            Path | None: SARIF output path or ``None`` when disabled.
        """

        return cast(Path | None, NotImplemented)

    @property
    def pr_summary_out(self) -> Path | None:
        """Return the path for PR summary artifacts.

        Returns:
            Path | None: PR summary output path or ``None`` when disabled.
        """

        return cast(Path | None, NotImplemented)

    @property
    def pr_summary_limit(self) -> int:
        """Return the maximum number of PR summary entries.

        Returns:
            int: Maximum number of PR summary entries.
        """

        return cast(int, NotImplemented)

    @property
    def pr_summary_min_severity(self) -> PrSummarySeverityLiteral:
        """Return the minimum severity included in PR summaries.

        Returns:
            PrSummarySeverityLiteral: Minimum severity that should be included.
        """

        return cast(PrSummarySeverityLiteral, NotImplemented)

    @property
    def pr_summary_template(self) -> str:
        """Return the template string used for PR summaries.

        Returns:
            str: Template string applied when writing PR summaries.
        """

        return cast(str, NotImplemented)

    @property
    def gha_annotations(self) -> bool:
        """Return whether GitHub Actions annotations should be emitted.

        Returns:
            bool: ``True`` when GitHub annotations are enabled.
        """

        return cast(bool, NotImplemented)

    @property
    def annotations_use_json(self) -> bool:
        """Return whether annotations should prefer JSON payloads.

        Returns:
            bool: ``True`` when annotations should be emitted as JSON.
        """

        return cast(bool, NotImplemented)


@runtime_checkable
class OutputConfig(OutputDisplayOptions, OutputArtifactOptions, Protocol):
    """Composite protocol combining display and artifact configuration options."""


@runtime_checkable
class ExecutionConfig(Protocol):
    """Execution-level toggles controlling tool selection and behaviour."""

    @property
    def only(self) -> Sequence[str]:
        """Return tool names explicitly included via configuration.

        Returns:
            Sequence[str]: tool names explicitly included via configuration.
        """
        return cast(Sequence[str], NotImplemented)

    @property
    def languages(self) -> Sequence[str]:
        """Return language filters constraining tool execution.

        Returns:
            Sequence[str]: language filters constraining tool execution.
        """
        return cast(Sequence[str], NotImplemented)

    @property
    def enable(self) -> Sequence[str]:
        """Return tool names forced on via configuration.

        Returns:
            Sequence[str]: tool names forced on via configuration.
        """
        return cast(Sequence[str], NotImplemented)

    @property
    def pyqa_rules(self) -> bool:
        """Return whether pyqa-specific rules are enabled.

        Returns:
            bool: whether pyqa-specific rules are enabled.
        """
        return cast(bool, NotImplemented)

    @pyqa_rules.setter
    def pyqa_rules(self, value: bool) -> None:
        """Update the pyqa rules toggle.

        Args:
            value: Desired pyqa rules state.
        """
        raise NotImplementedError

    @property
    def cache_enabled(self) -> bool:
        """Return whether caching is enabled.

        Returns:
            bool: whether caching is enabled.
        """
        return cast(bool, NotImplemented)

    @property
    def cache_dir(self) -> Path:
        """Return the cache directory.

        Returns:
            Path: the cache directory.
        """
        return cast(Path, NotImplemented)

    @property
    def jobs(self) -> int:
        """Return the maximum number of concurrent jobs.

        Returns:
            int: the maximum number of concurrent jobs.
        """
        return cast(int, NotImplemented)

    @property
    def bail(self) -> bool:
        """Return whether execution aborts on the first failure.

        Returns:
            bool: whether execution aborts on the first failure.
        """
        return cast(bool, NotImplemented)

    @property
    def strict(self) -> bool:
        """Return whether strict execution mode is enabled.

        Returns:
            bool: whether strict execution mode is enabled.
        """
        return cast(bool, NotImplemented)

    @property
    def fix_only(self) -> bool:
        """Return whether only fix-capable tools should run.

        Returns:
            bool: whether only fix-capable tools should run.
        """
        return cast(bool, NotImplemented)

    @property
    def check_only(self) -> bool:
        """Return whether only check actions should execute.

        Returns:
            bool: whether only check actions should execute.
        """
        return cast(bool, NotImplemented)

    @property
    def force_all(self) -> bool:
        """Return whether discovery heuristics are ignored.

        Returns:
            bool: whether discovery heuristics are ignored.
        """
        return cast(bool, NotImplemented)

    @property
    def respect_config(self) -> bool:
        """Return whether tool-specific config files must be honoured.

        Returns:
            bool: whether tool-specific config files must be honoured.
        """
        return cast(bool, NotImplemented)

    @property
    def use_local_linters(self) -> bool:
        """Return whether local linters may be used.

        Returns:
            bool: whether local linters may be used.
        """
        return cast(bool, NotImplemented)

    @property
    def line_length(self) -> int:
        """Return the canonical line length for tools.

        Returns:
            int: the canonical line length for tools.
        """
        return cast(int, NotImplemented)

    @property
    def sql_dialect(self) -> str:
        """Return the configured SQL dialect.

        Returns:
            str: the configured SQL dialect.
        """
        return cast(str, NotImplemented)

    @property
    def python_version(self) -> str | None:
        """Return the target Python version when specified.

        Returns:
            str | None: the target Python version when specified.
        """
        return cast(str | None, NotImplemented)


@runtime_checkable
class QualityConfig(Protocol):
    """Quality configuration surface used by the CLI."""

    @property
    def checks(self) -> Sequence[str]:
        """Return the ordered quality checks that should execute.

        Returns:
            Sequence[str]: the ordered quality checks that should execute.
        """
        return cast(Sequence[str], NotImplemented)

    @property
    def enforce_in_lint(self) -> bool:
        """Return whether quality checks run during lint commands.

        Returns:
            bool: whether quality checks run during lint commands.
        """
        return cast(bool, NotImplemented)

    @enforce_in_lint.setter
    def enforce_in_lint(self, value: bool) -> None:
        """Update the lint enforcement toggle.

        Args:
            value: Desired enforcement state.
        """
        ...

    @property
    def skip_globs(self) -> Sequence[str]:
        """Return glob patterns ignored by quality checks.

        Returns:
            Sequence[str]: glob patterns ignored by quality checks.
        """
        return cast(Sequence[str], NotImplemented)

    @skip_globs.setter
    def skip_globs(self, value: Sequence[str]) -> None:
        """Update the glob patterns skipped by quality checks.

        Args:
            value: Sequence of glob patterns to assign.
        """
        raise NotImplementedError

    @property
    def schema_targets(self) -> Sequence[Path]:
        """Return schema targets requiring validation.

        Returns:
            Sequence[Path]: schema targets requiring validation.
        """
        return cast(Sequence[Path], NotImplemented)

    @property
    def warn_file_size(self) -> int:
        """Return the file size threshold that emits warnings.

        Returns:
            int: the file size threshold that emits warnings.
        """
        return cast(int, NotImplemented)

    @property
    def max_file_size(self) -> int:
        """Return the maximum permitted file size.

        Returns:
            int: the maximum permitted file size.
        """
        return cast(int, NotImplemented)

    @property
    def protected_branches(self) -> Sequence[str]:
        """Return branches protected by quality enforcement.

        Returns:
            Sequence[str]: branches protected by quality enforcement.
        """
        return cast(Sequence[str], NotImplemented)


@runtime_checkable
class SupportsModelCopy(Protocol):
    """Protocol for configuration sections supporting ``model_copy``."""

    def model_copy(
        self,
        *,
        update: Mapping[str, ConfigValue] | None = None,
        deep: bool = False,
    ) -> Self:
        """Return a mutated copy of the configuration section.

        Args:
            update: Optional mapping of field updates to apply.
            deep: When ``True`` perform a deep copy instead of a shallow copy.

        Returns:
            Self: Updated configuration section copy.
        """
        raise NotImplementedError

    def model_dump(self) -> Mapping[str, ConfigValue]:
        """Return a mapping representation of the configuration section.

        Returns:
            Mapping[str, ConfigValue]: Mapping representation of the configuration section.
        """
        return cast(Mapping[str, ConfigValue], NotImplemented)


@runtime_checkable
class SeverityConfig(SupportsModelCopy, Protocol):
    """Severity thresholds shared across tools."""

    @property
    def sensitivity(self) -> SensitivityLevelLiteral:
        """Return the configured sensitivity level.

        Returns:
            SensitivityLevelLiteral: the configured sensitivity level.
        """
        return cast(SensitivityLevelLiteral, NotImplemented)

    @property
    def bandit_level(self) -> str:
        """Return the Bandit severity level.

        Returns:
            str: the Bandit severity level.
        """
        return cast(str, NotImplemented)

    @property
    def bandit_confidence(self) -> str:
        """Return the Bandit confidence level.

        Returns:
            str: the Bandit confidence level.
        """
        return cast(str, NotImplemented)

    @property
    def pylint_fail_under(self) -> float | None:
        """Return the Pylint fail-under score.

        Returns:
            float | None: the Pylint fail-under score.
        """
        return cast(float | None, NotImplemented)

    @property
    def max_warnings(self) -> int | None:
        """Return the maximum tolerated warnings.

        Returns:
            int | None: the maximum tolerated warnings.
        """
        return cast(int | None, NotImplemented)


@runtime_checkable
class StrictnessConfig(SupportsModelCopy, Protocol):
    """Type-checking strictness controls shared by tools."""

    @property
    def type_checking(self) -> str:
        """Return the strictness level identifier.

        Returns:
            str: the strictness level identifier.
        """
        return cast(str, NotImplemented)


@runtime_checkable
class ComplexityConfig(SupportsModelCopy, Protocol):
    """Complexity thresholds applied to compatible tools."""

    @property
    def max_complexity(self) -> int | None:
        """Return the maximum permitted cyclomatic complexity.

        Returns:
            int | None: the maximum permitted cyclomatic complexity.
        """
        return cast(int | None, NotImplemented)

    @property
    def max_arguments(self) -> int | None:
        """Return the maximum positional argument count.

        Returns:
            int | None: the maximum positional argument count.
        """
        return cast(int | None, NotImplemented)


@runtime_checkable
class Config(Protocol):
    """Minimal protocol describing the effective configuration container."""

    output: OutputConfig
    execution: ExecutionConfig
    quality: QualityConfig
    license: LicenseConfig
    file_discovery: FileDiscoveryConfig
    severity: SeverityConfig
    strictness: StrictnessConfig
    complexity: ComplexityConfig
    dedupe: DedupeConfig
    clean: CleanConfig
    update: UpdateConfig
    tool_settings: dict[str, dict[str, ConfigValue]]
    severity_rules: Sequence[str]

    def apply_sensitivity_profile(self, *, cli_overrides: Collection[str] | None = None) -> None:
        """Apply sensitivity presets to shared configuration knobs.

        Args:
            cli_overrides: Optional override names provided by the CLI that should
                be respected when applying sensitivity settings.
        """
        raise NotImplementedError

    def apply_shared_defaults(
        self,
        *,
        override: bool = False,
        baseline: SharedKnobSnapshot | None = None,
    ) -> None:
        """Propagate shared defaults into tool-specific settings.

        Args:
            override: When ``True`` overwrite existing tool-specific values.
            baseline: Optional snapshot used to restore shared defaults.
        """
        raise NotImplementedError

    def snapshot_shared_knobs(self) -> SharedKnobSnapshot:
        """Capture shared knob values for later comparison.

        Returns:
            SharedKnobSnapshot: Snapshot capturing the shared knob values.
        """
        return cast(SharedKnobSnapshot, NotImplemented)


@runtime_checkable
class ConfigSource(Protocol):
    """Provide configuration data loaded from disk or other mediums."""

    name: str
    """Identifier describing the configuration source."""

    @abstractmethod
    def load(self) -> ConfigFragment:
        """Provide configuration values as a mapping.

        Returns:
            ConfigFragment: Mapping containing configuration values.
        """

    @abstractmethod
    def describe(self) -> str:
        """Return a human-readable description of the source.

        Returns:
            str: Human-readable description of the source.
        """


@runtime_checkable
class ConfigResolver(Protocol):
    """Resolve layered configuration values into a final mapping."""

    @property
    @abstractmethod
    def strategy_name(self) -> str:
        """Return the resolver strategy identifier.

        Returns:
            str: Resolver strategy identifier.
        """

    @abstractmethod
    def resolve(self, *sources: ConfigFragment) -> ConfigFragment:
        """Merge ``sources`` according to resolver semantics.

        Args:
            sources: Configuration mappings to merge in priority order.

        Returns:
            ConfigFragment: Mapping containing the merged configuration payload.
        """


@runtime_checkable
class ConfigMutator(Protocol):
    """Apply overrides to configuration structures."""

    @property
    @abstractmethod
    def description(self) -> str:
        """Return a human-readable description of the mutator.

        Returns:
            str: Human-readable description of the mutator.
        """

    @abstractmethod
    def apply(self, data: MutableConfigFragment) -> None:
        """Apply mutations to ``data`` in place.

        Args:
            data: Mutable mapping that should be updated by the mutator.
        """


@runtime_checkable
class ConfigLoader(Protocol):
    """Define an interface that loads configuration values from registered sources."""

    @property
    @abstractmethod
    def target_name(self) -> str:
        """Return the name of the configuration target being loaded.

        Returns:
            str: Name of the configuration target being loaded.
        """

    @abstractmethod
    def load(self, *, strict: bool = False) -> Config:
        """Load the resolved configuration object.

        Args:
            strict: When ``True`` enforce strict validation semantics.

        Returns:
            Config: Fully resolved configuration container.
        """


__all__ = [
    "Config",
    "ConfigLoader",
    "ConfigMutator",
    "ConfigResolver",
    "ConfigSource",
    "ComplexityConfig",
    "ExecutionConfig",
    "OutputConfig",
    "QualityConfig",
    "SeverityConfig",
    "SharedKnobSnapshot",
    "SharedKnobValue",
    "StrictnessConfig",
    "SupportsModelCopy",
]
