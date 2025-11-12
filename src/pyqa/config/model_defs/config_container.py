# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Provide the aggregate configuration container and related helpers."""

from __future__ import annotations

from collections.abc import Collection, Mapping, MutableMapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Final, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

from tooling_spec.catalog.types import JSONValue as _CatalogJSONValue

from ...catalog.metadata import catalog_duplicate_preference
from ..models.sections import (
    CleanConfig,
    ComplexityConfig,
    DedupeConfig,
    ExecutionConfig,
    FileDiscoveryConfig,
    LicenseConfig,
    OutputConfig,
    QualityConfigSection,
    SeverityConfig,
    StrictnessConfig,
    UpdateConfig,
)
from ..types import ConfigValue
from .enums import BanditConfidence, BanditLevel, SensitivityLevel, StrictnessLevel
from .sentinels import NO_BASELINE, UNSET, ConfigSentinel
from .value_types import GenericValueTypesConfig

SensitivityOverrideValue = int | float | None | StrictnessLevel | BanditLevel | BanditConfidence
ToolOverrideValue = bool | int | float | str | Sequence[str] | None

MYPY_TOOL_KEY: Final[str] = "mypy"


def _default_tool_settings() -> dict[str, dict[str, ConfigValue]]:
    """Return baseline tool settings aligning with the legacy runner.

    Returns:
        dict[str, dict[str, ConfigValue]]: Mapping of tool identifiers to
        their default configuration payloads.

    """

    return {}


def _normalize_override_keys(
    cli_overrides: Collection[str] | None,
) -> set[ConfigOverrideKey]:
    """Return structured override keys derived from CLI tokens.

    Args:
        cli_overrides: Raw override tokens supplied via the command line.

    Returns:
        set[ConfigOverrideKey]: Recognised override keys corresponding to the
        provided CLI tokens.

    """

    overrides: set[ConfigOverrideKey] = set()
    if not cli_overrides:
        return overrides
    for token in cli_overrides:
        key = ConfigOverrideKey.from_raw(token)
        if key is not None:
            overrides.add(key)
    return overrides


def _load_duplicate_preference() -> tuple[str, ...]:
    """Return catalog-provided duplicate preference metadata.

    Returns:
        tuple[str, ...]: Ordered tool identifiers expressing duplicate
        resolution preference.

    """

    return catalog_duplicate_preference()


_MYPY_BASE_TRUE_FLAGS: Final[tuple[str, ...]] = (
    "exclude-gitignore",
    "sqlite-cache",
    "show-error-codes",
    "show-column-numbers",
)
_MYPY_STRICT_FLAGS: Final[tuple[str, ...]] = (
    "warn-redundant-casts",
    "warn-unused-ignores",
    "warn-unreachable",
    "disallow-untyped-decorators",
    "disallow-any-generics",
    "check-untyped-defs",
    "no-implicit-reexport",
)


def _expected_mypy_profile(strict_level: StrictnessLevel) -> dict[str, ConfigValue]:
    """Build the expected mypy settings for a given strictness level.

    Args:
        strict_level: Strictness profile used to derive default values.

    Returns:
        dict[str, ConfigValue]: Mapping of configuration keys to their default
        mypy values.

    """

    profile: dict[str, ConfigValue] = {flag: True for flag in _MYPY_BASE_TRUE_FLAGS}
    profile["strict"] = strict_level is StrictnessLevel.STRICT
    for flag in _MYPY_STRICT_FLAGS:
        profile[flag] = strict_level is StrictnessLevel.STRICT
    profile["ignore-missing-imports"] = strict_level is StrictnessLevel.LENIENT
    return profile


def _expected_mypy_value_for(
    key: str,
    strict_level: StrictnessLevel,
) -> ConfigValue | ConfigSentinel:
    """Return the default mypy setting for a specific configuration key.

    Args:
        key: Target mypy configuration option name.
        strict_level: Strictness profile used to derive defaults.

    Returns:
        ConfigValue | ConfigSentinel: Default value when known; otherwise
        ``NO_BASELINE``.

    """

    profile = _expected_mypy_profile(strict_level)
    return profile.get(key, NO_BASELINE)


class ConfigOverrideKey(str, Enum):
    """Define override keys recognised by sensitivity profiles."""

    LINE_LENGTH = "line_length"
    MAX_COMPLEXITY = "max_complexity"
    MAX_ARGUMENTS = "max_arguments"
    TYPE_CHECKING = "type_checking"
    BANDIT_LEVEL = "bandit_severity"
    BANDIT_CONFIDENCE = "bandit_confidence"
    PYLINT_FAIL_UNDER = "pylint_fail_under"
    MAX_WARNINGS = "max_warnings"

    @classmethod
    def from_raw(cls, raw: str) -> ConfigOverrideKey | None:
        """Return the enum member matching a raw CLI override token.

        Args:
            raw: String token supplied via CLI overrides.

        Returns:
            ConfigOverrideKey | None: Matching enum instance when recognised;
            otherwise ``None``.

        """

        try:
            return cls(raw)
        except ValueError:
            return None

    def apply(self, config: Config, value: SensitivityOverrideValue) -> None:
        """Apply the override value to the appropriate config section.

        Args:
            config: Configuration instance receiving the override.
            value: Override value resolved from the sensitivity preset.

        """

        if self is ConfigOverrideKey.LINE_LENGTH:
            numeric_value = cast(int | float, value)
            config.execution = config.execution.model_copy(
                update={"line_length": int(numeric_value)},
            )
        elif self is ConfigOverrideKey.MAX_COMPLEXITY:
            config.complexity = config.complexity.model_copy(
                update={"max_complexity": cast(int | None, value)},
            )
        elif self is ConfigOverrideKey.MAX_ARGUMENTS:
            config.complexity = config.complexity.model_copy(
                update={"max_arguments": cast(int | None, value)},
            )
        elif self is ConfigOverrideKey.TYPE_CHECKING:
            config.strictness = config.strictness.model_copy(
                update={"type_checking": cast(StrictnessLevel, value)},
            )
        elif self is ConfigOverrideKey.BANDIT_LEVEL:
            config.update_severity(bandit_level=cast(BanditLevel, value))
        elif self is ConfigOverrideKey.BANDIT_CONFIDENCE:
            config.update_severity(bandit_confidence=cast(BanditConfidence, value))
        elif self is ConfigOverrideKey.PYLINT_FAIL_UNDER:
            config.update_severity(pylint_fail_under=cast(float | None, value))
        elif self is ConfigOverrideKey.MAX_WARNINGS:
            config.update_severity(max_warnings=cast(int | None, value))


@dataclass(frozen=True, slots=True)
class ToolSpecificOverride:
    """Describe a tool-specific override applied by sensitivity presets."""

    key: str
    value: ToolOverrideValue
    skip_if_truthy: bool = False

    def apply(self, tool_settings: MutableMapping[str, ConfigValue]) -> None:
        """Apply the configured override onto a tool-specific mapping.

        Args:
            tool_settings: Mutable mapping of tool configuration values.

        """

        existing = tool_settings.get(self.key, UNSET)
        if existing is not UNSET:
            if self.skip_if_truthy and bool(existing):
                return
            if not self.skip_if_truthy:
                return
        if isinstance(self.value, Sequence) and not isinstance(self.value, (str, bytes)):
            tool_settings[self.key] = list(self.value)
        else:
            tool_settings[self.key] = self.value


@dataclass(frozen=True, slots=True)
class SensitivityPreset:
    """Define sensitivity-driven configuration preset values."""

    config_overrides: Mapping[ConfigOverrideKey, SensitivityOverrideValue] = field(
        default_factory=dict,
    )
    tool_overrides: Mapping[str, tuple[ToolSpecificOverride, ...]] = field(default_factory=dict)

    def apply(
        self,
        config: Config,
        *,
        skip_keys: set[ConfigOverrideKey],
    ) -> None:
        """Apply overrides contained in the preset to the provided config.

        Args:
            config: Configuration instance receiving the preset overrides.
            skip_keys: Override keys that should be skipped due to CLI input.

        """

        for key, value in self.config_overrides.items():
            if key in skip_keys:
                continue
            key.apply(config, value)
        for tool, overrides in self.tool_overrides.items():
            tool_settings = config.tool_settings.setdefault(tool, {})
            for override in overrides:
                override.apply(tool_settings)


SENSITIVITY_PRESETS: Final[dict[SensitivityLevel, SensitivityPreset]] = {
    SensitivityLevel.LOW: SensitivityPreset(
        config_overrides={
            ConfigOverrideKey.LINE_LENGTH: 140,
            ConfigOverrideKey.MAX_COMPLEXITY: 15,
            ConfigOverrideKey.MAX_ARGUMENTS: 7,
            ConfigOverrideKey.TYPE_CHECKING: StrictnessLevel.LENIENT,
            ConfigOverrideKey.BANDIT_LEVEL: BanditLevel.LOW,
            ConfigOverrideKey.BANDIT_CONFIDENCE: BanditConfidence.LOW,
            ConfigOverrideKey.PYLINT_FAIL_UNDER: 8.0,
            ConfigOverrideKey.MAX_WARNINGS: 200,
        },
    ),
    SensitivityLevel.MEDIUM: SensitivityPreset(
        config_overrides={
            ConfigOverrideKey.LINE_LENGTH: 120,
            ConfigOverrideKey.MAX_COMPLEXITY: 10,
            ConfigOverrideKey.MAX_ARGUMENTS: 5,
            ConfigOverrideKey.TYPE_CHECKING: StrictnessLevel.STRICT,
            ConfigOverrideKey.BANDIT_LEVEL: BanditLevel.MEDIUM,
            ConfigOverrideKey.BANDIT_CONFIDENCE: BanditConfidence.MEDIUM,
            ConfigOverrideKey.PYLINT_FAIL_UNDER: 9.5,
            ConfigOverrideKey.MAX_WARNINGS: None,
        },
    ),
    SensitivityLevel.HIGH: SensitivityPreset(
        config_overrides={
            ConfigOverrideKey.LINE_LENGTH: 110,
            ConfigOverrideKey.MAX_COMPLEXITY: 8,
            ConfigOverrideKey.MAX_ARGUMENTS: 4,
            ConfigOverrideKey.TYPE_CHECKING: StrictnessLevel.STRICT,
            ConfigOverrideKey.BANDIT_LEVEL: BanditLevel.HIGH,
            ConfigOverrideKey.BANDIT_CONFIDENCE: BanditConfidence.HIGH,
            ConfigOverrideKey.PYLINT_FAIL_UNDER: 9.75,
            ConfigOverrideKey.MAX_WARNINGS: 5,
        },
    ),
    SensitivityLevel.MAXIMUM: SensitivityPreset(
        config_overrides={
            ConfigOverrideKey.LINE_LENGTH: 100,
            ConfigOverrideKey.MAX_COMPLEXITY: 6,
            ConfigOverrideKey.MAX_ARGUMENTS: 3,
            ConfigOverrideKey.TYPE_CHECKING: StrictnessLevel.STRICT,
            ConfigOverrideKey.BANDIT_LEVEL: BanditLevel.HIGH,
            ConfigOverrideKey.BANDIT_CONFIDENCE: BanditConfidence.HIGH,
            ConfigOverrideKey.PYLINT_FAIL_UNDER: 9.9,
            ConfigOverrideKey.MAX_WARNINGS: 0,
        },
        tool_overrides={
            "ruff": (ToolSpecificOverride(key="select", value=("ALL",), skip_if_truthy=True),),
            "pylint": (ToolSpecificOverride(key="init-import", value=True),),
        },
    ),
}

_STRICT_DEDUPE_SENSITIVITY_LEVELS: Final[set[SensitivityLevel]] = {
    SensitivityLevel.HIGH,
    SensitivityLevel.MAXIMUM,
}

_TOOL_KNOB_MAPPING: Final[dict[tuple[str, str], ConfigOverrideKey]] = {
    ("black", "line-length"): ConfigOverrideKey.LINE_LENGTH,
    ("isort", "line-length"): ConfigOverrideKey.LINE_LENGTH,
    ("ruff", "line-length"): ConfigOverrideKey.LINE_LENGTH,
    ("ruff-format", "line-length"): ConfigOverrideKey.LINE_LENGTH,
    ("pylint", "max-line-length"): ConfigOverrideKey.LINE_LENGTH,
    ("luacheck", "max-line-length"): ConfigOverrideKey.LINE_LENGTH,
    ("luacheck", "max-code-line-length"): ConfigOverrideKey.LINE_LENGTH,
    ("luacheck", "max-string-line-length"): ConfigOverrideKey.LINE_LENGTH,
    ("luacheck", "max-comment-line-length"): ConfigOverrideKey.LINE_LENGTH,
    ("prettier", "print-width"): ConfigOverrideKey.LINE_LENGTH,
    ("pylint", "max-complexity"): ConfigOverrideKey.MAX_COMPLEXITY,
    ("luacheck", "max-cyclomatic-complexity"): ConfigOverrideKey.MAX_COMPLEXITY,
    ("pylint", "max-args"): ConfigOverrideKey.MAX_ARGUMENTS,
    ("pylint", "max-positional-arguments"): ConfigOverrideKey.MAX_ARGUMENTS,
    ("bandit", "severity"): ConfigOverrideKey.BANDIT_LEVEL,
    ("bandit", "confidence"): ConfigOverrideKey.BANDIT_CONFIDENCE,
    ("pylint", "fail-under"): ConfigOverrideKey.PYLINT_FAIL_UNDER,
    ("stylelint", "max-warnings"): ConfigOverrideKey.MAX_WARNINGS,
    ("eslint", "max-warnings"): ConfigOverrideKey.MAX_WARNINGS,
}


@dataclass(frozen=True, slots=True)
class SharedKnobSnapshot:
    """Capture shared configuration knob values prior to recalculation."""

    knob_values: Mapping[ConfigOverrideKey, SensitivityOverrideValue]
    pylint_init_import: bool | None

    def value_for(self, tool: str, key: str) -> ConfigValue | ConfigSentinel:
        """Return the baseline value for the given tool configuration key.

        Args:
            tool: Identifier for the tool requesting a baseline value.
            key: Tool-specific configuration option identifier.

        Returns:
            ConfigValue | ConfigSentinel: Baseline value when maintained, or
            ``NO_BASELINE`` when unmanaged.

        """

        mapping_key = (tool, key)
        if mapping_key in _TOOL_KNOB_MAPPING:
            knob = _TOOL_KNOB_MAPPING[mapping_key]
            return self._normalise_value(self.knob_values.get(knob, NO_BASELINE))
        if mapping_key == ("pylint", "init-import"):
            return self.pylint_init_import if self.pylint_init_import is not None else NO_BASELINE
        if mapping_key == ("tsc", "strict"):
            strictness = cast(
                StrictnessLevel,
                self.knob_values.get(
                    ConfigOverrideKey.TYPE_CHECKING,
                    StrictnessLevel.STANDARD,
                ),
            )
            return strictness is StrictnessLevel.STRICT
        if tool == MYPY_TOOL_KEY:
            strictness = cast(
                StrictnessLevel,
                self.knob_values.get(
                    ConfigOverrideKey.TYPE_CHECKING,
                    StrictnessLevel.STANDARD,
                ),
            )
            return _expected_mypy_value_for(key, strictness)
        return NO_BASELINE

    @staticmethod
    def _normalise_value(
        value: ConfigValue | Enum | ConfigSentinel,
    ) -> ConfigValue | ConfigSentinel:
        """Convert enum values to their serialisable counterparts.

        Args:
            value: Raw value retrieved from the snapshot mapping.

        Returns:
            ConfigValue | ConfigSentinel: Serialisable value suitable for
            downstream comparisons.

        """

        if isinstance(value, Enum):
            return cast(ConfigValue, value.value)
        return value


class Config(BaseModel):
    """Aggregate orchestrator configuration into a single container."""

    model_config = ConfigDict(validate_assignment=True)

    file_discovery: FileDiscoveryConfig = Field(default_factory=FileDiscoveryConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)
    dedupe: DedupeConfig = Field(default_factory=DedupeConfig)
    severity_rules: list[str] = Field(default_factory=list)
    tool_settings: dict[str, dict[str, ConfigValue]] = Field(default_factory=_default_tool_settings)
    license: LicenseConfig = Field(default_factory=LicenseConfig)
    quality: QualityConfigSection = Field(default_factory=QualityConfigSection)
    generic_value_types: GenericValueTypesConfig = Field(default_factory=GenericValueTypesConfig)
    clean: CleanConfig = Field(default_factory=CleanConfig)
    update: UpdateConfig = Field(default_factory=UpdateConfig)
    complexity: ComplexityConfig = Field(default_factory=ComplexityConfig)
    strictness: StrictnessConfig = Field(default_factory=StrictnessConfig)
    severity: SeverityConfig = Field(default_factory=SeverityConfig)

    def to_dict(self) -> dict[str, ConfigValue]:
        """Return a dictionary representation suitable for serialization.

        Returns:
            dict[str, ConfigValue]: Serialisable mapping of configuration
            values.

        """

        payload: dict[str, ConfigValue] = dict(self.model_dump(mode="python"))
        payload["severity_rules"] = list(self.severity_rules)
        raw_tool_settings = payload.get("tool_settings", {})
        if isinstance(raw_tool_settings, dict):
            tool_settings_map: dict[str, dict[str, ConfigValue]] = {}
            for tool, settings in raw_tool_settings.items():
                if isinstance(settings, dict):
                    tool_settings_map[str(tool)] = dict(settings.items())
            payload["tool_settings"] = tool_settings_map
        quality_section = payload.get("quality", {})
        if isinstance(quality_section, dict):
            quality_section["schema_targets"] = [str(path) for path in self.quality.schema_targets]
            payload["quality"] = quality_section
        return payload

    @model_validator(mode="after")
    def _apply_defaults_post_validation(self) -> Config:
        """Apply derived defaults after model validation.

        Returns:
            Config: Configuration instance with shared defaults applied.

        """

        self.apply_shared_defaults()
        return self

    def apply_sensitivity_profile(
        self,
        *,
        cli_overrides: Collection[str] | None = None,
    ) -> None:
        """Apply sensitivity presets to shared configuration knobs.

        Args:
            cli_overrides: Raw override tokens supplied by the CLI to opt out
                of specific preset-provided values.

        """

        preset = SENSITIVITY_PRESETS.get(self.severity.sensitivity)
        if preset is None:
            return
        override_keys = _normalize_override_keys(cli_overrides)
        preset.apply(self, skip_keys=override_keys)
        if self.severity.sensitivity in _STRICT_DEDUPE_SENSITIVITY_LEVELS:
            self._enable_strict_dedupe()

    def snapshot_shared_knobs(self) -> SharedKnobSnapshot:
        """Capture the shared knob values to compare during recalculation.

        Returns:
            SharedKnobSnapshot: Immutable snapshot of shared configuration
            settings that influence multiple tools.

        """

        knob_values: dict[ConfigOverrideKey, SensitivityOverrideValue] = {
            ConfigOverrideKey.LINE_LENGTH: self.execution.line_length,
            ConfigOverrideKey.MAX_COMPLEXITY: self.complexity.max_complexity,
            ConfigOverrideKey.MAX_ARGUMENTS: self.complexity.max_arguments,
            ConfigOverrideKey.TYPE_CHECKING: self.strictness.type_checking,
            ConfigOverrideKey.BANDIT_LEVEL: self.severity.bandit_level,
            ConfigOverrideKey.BANDIT_CONFIDENCE: self.severity.bandit_confidence,
            ConfigOverrideKey.PYLINT_FAIL_UNDER: self.severity.pylint_fail_under,
            ConfigOverrideKey.MAX_WARNINGS: self.severity.max_warnings,
        }
        pylint_init_import = cast(
            bool | None,
            self.tool_settings.get("pylint", {}).get("init-import"),
        )
        return SharedKnobSnapshot(
            knob_values=knob_values,
            pylint_init_import=pylint_init_import,
        )

    def apply_shared_defaults(
        self,
        *,
        override: bool = False,
        baseline: SharedKnobSnapshot | None = None,
    ) -> None:
        """Ensure shared configuration defaults are reflected in tool settings.

        Args:
            override: When ``True`` apply updates even when settings exist.
            baseline: Snapshot representing previously applied shared values.

        """

        duplicate_preference = _load_duplicate_preference()
        if duplicate_preference:
            self._merge_dedupe_preferences(duplicate_preference)
        self._apply_mypy_defaults(override=override, baseline=baseline)

    def update_severity(
        self,
        *,
        bandit_level: BanditLevel | ConfigSentinel = UNSET,
        bandit_confidence: BanditConfidence | ConfigSentinel = UNSET,
        pylint_fail_under: float | None | ConfigSentinel = UNSET,
        max_warnings: int | None | ConfigSentinel = UNSET,
    ) -> None:
        """Apply targeted updates to the severity configuration section.

        Args:
            bandit_level: Optional override for Bandit's severity level.
            bandit_confidence: Optional override for Bandit's confidence level.
            pylint_fail_under: Optional override for Pylint's fail-under score.
            max_warnings: Optional override for maximum tolerable warnings.

        """

        self._update_severity(
            bandit_level=bandit_level,
            bandit_confidence=bandit_confidence,
            pylint_fail_under=pylint_fail_under,
            max_warnings=max_warnings,
        )

    def _update_severity(
        self,
        *,
        bandit_level: BanditLevel | ConfigSentinel = UNSET,
        bandit_confidence: BanditConfidence | ConfigSentinel = UNSET,
        pylint_fail_under: float | None | ConfigSentinel = UNSET,
        max_warnings: int | None | ConfigSentinel = UNSET,
    ) -> None:
        """Apply targeted updates to the severity configuration section.

        Args:
            bandit_level: Optional override for Bandit's severity level.
            bandit_confidence: Optional override for Bandit's confidence level.
            pylint_fail_under: Optional override for Pylint's fail-under score.
            max_warnings: Optional override for maximum tolerable warnings.

        """

        updates: dict[str, ConfigValue | None] = {}
        if bandit_level is not UNSET:
            updates["bandit_level"] = cast(ConfigValue, bandit_level)
        if bandit_confidence is not UNSET:
            updates["bandit_confidence"] = cast(ConfigValue, bandit_confidence)
        if pylint_fail_under is not UNSET:
            updates["pylint_fail_under"] = cast(float | None, pylint_fail_under)
        if max_warnings is not UNSET:
            updates["max_warnings"] = cast(int | None, max_warnings)
        if updates:
            self.severity = self.severity.model_copy(update=updates)

    def _enable_strict_dedupe(self) -> None:
        """Tighten dedupe behaviour for strict sensitivity presets."""

        self.dedupe.dedupe = True
        self.dedupe.dedupe_by = "prefer"
        prefer_list = list(self.dedupe.dedupe_prefer)
        for tool_name in ("pyright", "mypy"):
            if tool_name not in prefer_list:
                prefer_list.append(tool_name)
        self.dedupe.dedupe_prefer = prefer_list

    def _merge_dedupe_preferences(self, preferred_order: Sequence[str]) -> None:
        """Merge dedupe preferences using catalog-provided ordering.

        Args:
            preferred_order: Ordered sequence of tool identifiers drawn from
                catalog metadata.

        """

        prefer_list = list(self.dedupe.dedupe_prefer)
        for tool_name in preferred_order:
            if tool_name not in prefer_list:
                prefer_list.append(tool_name)
        self.dedupe.dedupe_prefer = prefer_list

    def _apply_mypy_defaults(
        self,
        *,
        override: bool,
        baseline: SharedKnobSnapshot | None,
    ) -> None:
        """Synchronize mypy configuration defaults with shared settings.

        Args:
            override: When ``True`` apply updates even when settings exist.
            baseline: Prior snapshot to respect manual adjustments.

        """

        mypy_settings = self.tool_settings.setdefault("mypy", {})
        baseline_profile: Mapping[str, ConfigValue] = {}
        strictness = self.strictness.type_checking
        if baseline is not None:
            strictness = cast(
                StrictnessLevel,
                baseline.knob_values.get(
                    ConfigOverrideKey.TYPE_CHECKING,
                    strictness,
                ),
            )
            baseline_profile = _expected_mypy_profile(strictness)
        manager = _MypySettingManager(
            settings=mypy_settings,
            baseline=baseline_profile,
            override=override,
        )
        for key in _MYPY_BASE_TRUE_FLAGS:
            manager.set_default(key, True)
        manager.set_default("strict", None)
        for key in _MYPY_STRICT_FLAGS:
            manager.set_default(key, None)
        manager.set_default("ignore-missing-imports", None)


@dataclass(slots=True)
class _MypySettingManager:
    """Manage mypy defaults while respecting override semantics."""

    settings: dict[str, ConfigValue]
    baseline: Mapping[str, ConfigValue]
    override: bool

    def set_default(self, key: str, value: ConfigValue | None) -> None:
        """Set or remove a mypy setting following override rules.

        Args:
            key: Name of the mypy configuration option to manage.
            value: Desired default value or ``None`` to remove the key.

        """

        existing: ConfigValue | ConfigSentinel = self.settings.get(key, UNSET)
        baseline_value: ConfigValue | ConfigSentinel = self.baseline.get(key, NO_BASELINE)
        if value is None:
            if self.override and (
                existing is UNSET or (baseline_value is not NO_BASELINE and existing != baseline_value)
            ):
                return
            self.settings.pop(key, None)
            return
        if self.override and existing is not UNSET and baseline_value is not NO_BASELINE and existing != baseline_value:
            return
        if self.override or existing is UNSET:
            self.settings[key] = value


Config.model_rebuild(_types_namespace={"JSONValue": _CatalogJSONValue})

__all__ = [
    "Config",
    "ConfigOverrideKey",
    "MYPY_TOOL_KEY",
    "SENSITIVITY_PRESETS",
    "SensitivityOverrideValue",
    "SensitivityPreset",
    "SharedKnobSnapshot",
    "ToolOverrideValue",
    "ToolSpecificOverride",
    "_STRICT_DEDUPE_SENSITIVITY_LEVELS",
    "_TOOL_KNOB_MAPPING",
]
