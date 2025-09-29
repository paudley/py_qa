# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Configuration models and helpers for the pyqa lint orchestration package."""

from __future__ import annotations

import math
import os
from collections.abc import Collection
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal, cast

from pydantic import BaseModel, ConfigDict, Field


class ConfigError(Exception):
    """Raised when configuration input is invalid."""


def default_parallel_jobs() -> int:
    """Return 75% of available CPU cores (minimum of 1)."""
    cores = os.cpu_count() or 1
    proposed = max(1, math.floor(cores * 0.75))
    return proposed


def _expected_mypy_profile(
    strict_level: Literal["lenient", "standard", "strict"],
) -> dict[str, object]:
    """Return the expected mypy settings for a given strictness level."""
    profile: dict[str, object] = {
        "exclude-gitignore": True,
        "sqlite-cache": True,
        "show-error-codes": True,
        "show-column-numbers": True,
        "strict": strict_level == "strict",
    }
    strict_flags = (
        "warn-redundant-casts",
        "warn-unused-ignores",
        "warn-unreachable",
        "disallow-untyped-decorators",
        "disallow-any-generics",
        "check-untyped-defs",
        "no-implicit-reexport",
    )
    if strict_level == "strict":
        for flag in strict_flags:
            profile[flag] = True
    else:
        for flag in strict_flags:
            profile[flag] = False
    if strict_level == "lenient":
        profile["ignore-missing-imports"] = True
    else:
        profile["ignore-missing-imports"] = False
    return profile


def _expected_mypy_value_for(
    key: str,
    strict_level: Literal["lenient", "standard", "strict"],
) -> object:
    profile = _expected_mypy_profile(strict_level)
    return profile.get(key, NO_BASELINE)


class FileDiscoveryConfig(BaseModel):
    """Configuration for how to discover and filter files within a project."""

    model_config = ConfigDict(validate_assignment=True)

    roots: list[Path] = Field(default_factory=lambda: [Path()])
    excludes: list[Path] = Field(default_factory=list)
    paths_from_stdin: bool = False
    changed_only: bool = False
    diff_ref: str = "HEAD"
    include_untracked: bool = True
    base_branch: str | None = None
    pre_commit: bool = False
    respect_gitignore: bool = False
    explicit_files: list[Path] = Field(default_factory=list)
    limit_to: list[Path] = Field(default_factory=list)


class OutputConfig(BaseModel):
    """Configuration for controlling output, reporting, and artifact creation."""

    model_config = ConfigDict(validate_assignment=True)

    verbose: bool = False
    emoji: bool = True
    color: bool = True
    show_passing: bool = False
    show_stats: bool = True
    output: Literal["pretty", "raw", "concise"] = "concise"
    pretty_format: Literal["text", "jsonl", "markdown"] = "text"
    group_by_code: bool = False
    report: Literal["json"] | None = None
    report_out: Path | None = None
    report_include_raw: bool = False
    sarif_out: Path | None = None
    pr_summary_out: Path | None = None
    pr_summary_limit: int = 100
    pr_summary_min_severity: Literal["error", "warning", "notice", "note"] = "warning"
    pr_summary_template: str = "- **{severity}** `{tool}` {message} ({location})"
    gha_annotations: bool = False
    annotations_use_json: bool = False
    quiet: bool = False
    tool_filters: dict[str, list[str]] = Field(default_factory=dict)
    advice: bool = False


class ExecutionConfig(BaseModel):
    """Execution behaviour and lint tool selection configuration."""

    model_config = ConfigDict(validate_assignment=True)

    only: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    enable: list[str] = Field(default_factory=list)
    strict: bool = False
    jobs: int = Field(default_factory=default_parallel_jobs)
    fix_only: bool = False
    check_only: bool = False
    force_all: bool = False
    respect_config: bool = False
    cache_enabled: bool = True
    cache_dir: Path = Field(default_factory=lambda: Path(".lint-cache"))
    bail: bool = False
    use_local_linters: bool = False
    line_length: int = 120
    sql_dialect: str = "postgresql"
    python_version: str | None = None


class DedupeConfig(BaseModel):
    """Configuration knobs for deduplicating diagnostics."""

    model_config = ConfigDict(validate_assignment=True)

    dedupe: bool = False
    dedupe_by: Literal["first", "severity", "prefer"] = "first"
    dedupe_prefer: list[str] = Field(default_factory=list)
    dedupe_line_fuzz: int = 2
    dedupe_same_file_only: bool = True


DEFAULT_QUALITY_CHECKS: Final[list[str]] = ["license", "file-size", "schema", "python"]
DEFAULT_SCHEMA_TARGETS: Final[list[Path]] = [Path("ref_docs/tool-schema.json")]
DEFAULT_PROTECTED_BRANCHES: Final[list[str]] = ["main", "master"]

DEFAULT_CLEAN_PATTERNS: Final[list[str]] = [
    "*.log",
    ".*cache",
    ".claude*.json",
    ".coverage",
    ".hypothesis",
    ".stream*.json",
    ".venv",
    "__pycache__",
    "chroma*db",
    "coverage*",
    "dist",
    "filesystem_store",
    "htmlcov*",
]

DEFAULT_CLEAN_TREES: Final[list[str]] = ["examples", "packages", "build"]

DEFAULT_UPDATE_SKIP_PATTERNS: Final[list[str]] = ["pyreadstat", ".git/modules"]


def _default_tool_settings() -> dict[str, dict[str, object]]:
    """Return baseline tool settings that mirror the legacy lint script."""
    return {}


class ComplexityConfig(BaseModel):
    """Shared complexity thresholds applied to compatible tools."""

    model_config = ConfigDict(validate_assignment=True)

    max_complexity: int | None = 10
    max_arguments: int | None = 5


class StrictnessConfig(BaseModel):
    """Shared strictness controls for type-checking tools."""

    model_config = ConfigDict(validate_assignment=True)

    type_checking: Literal["lenient", "standard", "strict"] = "standard"


class SeverityConfig(BaseModel):
    """Shared severity thresholds for supported tools."""

    model_config = ConfigDict(validate_assignment=True)

    bandit_level: Literal["low", "medium", "high"] = "medium"
    bandit_confidence: Literal["low", "medium", "high"] = "medium"
    pylint_fail_under: float | None = 9.5
    max_warnings: int | None = None
    sensitivity: Literal["low", "medium", "high", "maximum"] = "medium"


UNSET: Final[object] = object()
NO_BASELINE: Final[object] = object()


@dataclass(frozen=True)
class SensitivityPreset:
    """Preset values driven by overall sensitivity."""

    line_length: int | object = UNSET
    max_complexity: int | object = UNSET
    max_arguments: int | object = UNSET
    type_checking: Literal["lenient", "standard", "strict"] | object = UNSET
    bandit_level: Literal["low", "medium", "high"] | object = UNSET
    bandit_confidence: Literal["low", "medium", "high"] | object = UNSET
    pylint_fail_under: float | None | object = UNSET
    max_warnings: int | None | object = UNSET
    ruff_select: tuple[str, ...] | object = UNSET
    pylint_init_import: bool | object = UNSET


SENSITIVITY_PRESETS: Final[dict[str, SensitivityPreset]] = {
    "low": SensitivityPreset(
        line_length=140,
        max_complexity=15,
        max_arguments=7,
        type_checking="lenient",
        bandit_level="low",
        bandit_confidence="low",
        pylint_fail_under=8.0,
        max_warnings=200,
    ),
    "medium": SensitivityPreset(
        line_length=120,
        max_complexity=10,
        max_arguments=5,
        type_checking="strict",
        bandit_level="medium",
        bandit_confidence="medium",
        pylint_fail_under=9.5,
        max_warnings=None,
    ),
    "high": SensitivityPreset(
        line_length=110,
        max_complexity=8,
        max_arguments=4,
        type_checking="strict",
        bandit_level="high",
        bandit_confidence="high",
        pylint_fail_under=9.75,
        max_warnings=5,
    ),
    "maximum": SensitivityPreset(
        line_length=100,
        max_complexity=6,
        max_arguments=3,
        type_checking="strict",
        bandit_level="high",
        bandit_confidence="high",
        pylint_fail_under=9.9,
        max_warnings=0,
        ruff_select=("ALL",),
        pylint_init_import=True,
    ),
}


@dataclass(frozen=True)
class SharedKnobSnapshot:
    """Snapshot of shared configuration knobs before recalculating defaults."""

    line_length: int
    max_complexity: int | None
    max_arguments: int | None
    type_checking: Literal["lenient", "standard", "strict"]
    bandit_level: Literal["low", "medium", "high"]
    bandit_confidence: Literal["low", "medium", "high"]
    pylint_fail_under: float | None
    max_warnings: int | None
    pylint_init_import: bool | None

    def value_for(self, tool: str, key: str) -> object:
        mapping: dict[tuple[str, str], object] = {
            ("black", "line-length"): self.line_length,
            ("isort", "line-length"): self.line_length,
            ("ruff", "line-length"): self.line_length,
            ("ruff-format", "line-length"): self.line_length,
            ("pylint", "max-line-length"): self.line_length,
            ("luacheck", "max-line-length"): self.line_length,
            ("luacheck", "max-code-line-length"): self.line_length,
            ("luacheck", "max-string-line-length"): self.line_length,
            ("luacheck", "max-comment-line-length"): self.line_length,
            ("prettier", "print-width"): self.line_length,
            ("pylint", "max-complexity"): self.max_complexity,
            ("luacheck", "max-cyclomatic-complexity"): self.max_complexity,
            ("pylint", "max-args"): self.max_arguments,
            ("pylint", "max-positional-arguments"): self.max_arguments,
            ("bandit", "severity"): self.bandit_level,
            ("bandit", "confidence"): self.bandit_confidence,
            ("pylint", "fail-under"): self.pylint_fail_under,
            ("pylint", "init-import"): self.pylint_init_import,
            ("stylelint", "max-warnings"): self.max_warnings,
            ("eslint", "max-warnings"): self.max_warnings,
            ("tsc", "strict"): self.type_checking == "strict",
        }
        if (tool, key) in mapping:
            return mapping[(tool, key)]
        if tool == "mypy":
            return _expected_mypy_value_for(key, self.type_checking)
        return NO_BASELINE


class LicenseConfig(BaseModel):
    """Project-wide licensing policy configuration."""

    model_config = ConfigDict(validate_assignment=True)

    spdx: str | None = None
    notice: str | None = None
    copyright: str | None = None
    year: str | None = None
    require_spdx: bool = True
    require_notice: bool = True
    allow_alternate_spdx: list[str] = Field(default_factory=list)
    exceptions: list[str] = Field(default_factory=list)


class QualityConfigSection(BaseModel):
    """Quality enforcement configuration shared across commands."""

    model_config = ConfigDict(validate_assignment=True)

    checks: list[str] = Field(default_factory=lambda: list(DEFAULT_QUALITY_CHECKS))
    skip_globs: list[str] = Field(default_factory=list)
    schema_targets: list[Path] = Field(default_factory=lambda: list(DEFAULT_SCHEMA_TARGETS))
    warn_file_size: int = 5 * 1024 * 1024
    max_file_size: int = 10 * 1024 * 1024
    protected_branches: list[str] = Field(default_factory=lambda: list(DEFAULT_PROTECTED_BRANCHES))


class CleanConfig(BaseModel):
    """Configuration for repository cleanup patterns."""

    model_config = ConfigDict(validate_assignment=True)

    patterns: list[str] = Field(default_factory=lambda: list(DEFAULT_CLEAN_PATTERNS))
    trees: list[str] = Field(default_factory=lambda: list(DEFAULT_CLEAN_TREES))


class UpdateConfig(BaseModel):
    """Configuration for workspace dependency updates."""

    model_config = ConfigDict(validate_assignment=True)

    skip_patterns: list[str] = Field(default_factory=lambda: list(DEFAULT_UPDATE_SKIP_PATTERNS))
    enabled_managers: list[str] = Field(default_factory=list)


class Config(BaseModel):
    """Primary configuration container used by the orchestrator."""

    model_config = ConfigDict(validate_assignment=True)

    file_discovery: FileDiscoveryConfig = Field(default_factory=FileDiscoveryConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)
    dedupe: DedupeConfig = Field(default_factory=DedupeConfig)
    severity_rules: list[str] = Field(default_factory=list)
    tool_settings: dict[str, dict[str, object]] = Field(default_factory=_default_tool_settings)
    license: LicenseConfig = Field(default_factory=LicenseConfig)
    quality: QualityConfigSection = Field(default_factory=QualityConfigSection)
    clean: CleanConfig = Field(default_factory=CleanConfig)
    update: UpdateConfig = Field(default_factory=UpdateConfig)
    complexity: ComplexityConfig = Field(default_factory=ComplexityConfig)
    strictness: StrictnessConfig = Field(default_factory=StrictnessConfig)
    severity: SeverityConfig = Field(default_factory=SeverityConfig)

    def to_dict(self) -> dict[str, object]:
        """Return a dictionary representation suitable for serialization."""
        payload: dict[str, object] = dict(self.model_dump(mode="python"))
        payload["severity_rules"] = list(self.severity_rules)
        quality_cfg = cast("QualityConfigSection", self.quality)
        raw_tool_settings = payload.get("tool_settings", {})
        if isinstance(raw_tool_settings, dict):
            tool_settings_map: dict[str, dict[str, object]] = {}
            for tool, settings in raw_tool_settings.items():
                if isinstance(settings, dict):
                    tool_settings_map[str(tool)] = dict(settings.items())
            payload["tool_settings"] = tool_settings_map
        quality_section = payload.get("quality", {})
        if isinstance(quality_section, dict):
            schema_targets = getattr(quality_cfg, "schema_targets", [])
            quality_section["schema_targets"] = [str(path) for path in schema_targets]
            payload["quality"] = quality_section
        return payload

    def model_post_init(self, __context: Any) -> None:  # pragma: no cover - pydantic hook
        self.apply_shared_defaults()

    def apply_sensitivity_profile(self, *, cli_overrides: Collection[str] | None = None) -> None:
        """Mutate shared knobs based on the sensitivity preset."""
        preset = SENSITIVITY_PRESETS.get(self.severity.sensitivity)
        if preset is None:
            return

        overrides = set(cli_overrides or ())

        if preset.line_length is not UNSET and "line_length" not in overrides:
            self.execution.line_length = cast("int", preset.line_length)
        if preset.max_complexity is not UNSET and "max_complexity" not in overrides:
            self.complexity.max_complexity = cast("int", preset.max_complexity)
        if preset.max_arguments is not UNSET and "max_arguments" not in overrides:
            self.complexity.max_arguments = cast("int", preset.max_arguments)
        if preset.type_checking is not UNSET and "type_checking" not in overrides:
            self.strictness.type_checking = cast(
                "Literal['lenient', 'standard', 'strict']",
                preset.type_checking,
            )
        if preset.bandit_level is not UNSET and "bandit_severity" not in overrides:
            self.severity.bandit_level = cast("str", preset.bandit_level)
        if preset.bandit_confidence is not UNSET and "bandit_confidence" not in overrides:
            self.severity.bandit_confidence = cast("str", preset.bandit_confidence)
        if preset.pylint_fail_under is not UNSET and "pylint_fail_under" not in overrides:
            self.severity.pylint_fail_under = cast("float | None", preset.pylint_fail_under)
        if preset.max_warnings is not UNSET:
            self.severity.max_warnings = cast("int | None", preset.max_warnings)

        if preset.ruff_select is not UNSET:
            ruff_settings = self.tool_settings.setdefault("ruff", {})
            if not ruff_settings.get("select"):
                ruff_settings["select"] = list(cast("tuple[str, ...]", preset.ruff_select))
        if preset.pylint_init_import is not UNSET:
            pylint_settings = self.tool_settings.setdefault("pylint", {})
            if "init-import" not in pylint_settings:
                pylint_settings["init-import"] = cast("bool", preset.pylint_init_import)

        if self.severity.sensitivity in {"high", "maximum"}:
            self.dedupe.dedupe = True
            self.dedupe.dedupe_by = "prefer"
            prefer_list = list(self.dedupe.dedupe_prefer)
            for tool_name in ("mypy", "pyright"):
                if tool_name not in prefer_list:
                    prefer_list.append(tool_name)
            self.dedupe.dedupe_prefer = prefer_list

    def snapshot_shared_knobs(self) -> SharedKnobSnapshot:
        """Capture the shared knob values to compare during recalculation."""
        return SharedKnobSnapshot(
            line_length=self.execution.line_length,
            max_complexity=self.complexity.max_complexity,
            max_arguments=self.complexity.max_arguments,
            type_checking=self.strictness.type_checking,
            bandit_level=self.severity.bandit_level,
            bandit_confidence=self.severity.bandit_confidence,
            pylint_fail_under=self.severity.pylint_fail_under,
            max_warnings=self.severity.max_warnings,
            pylint_init_import=cast(
                "bool | None",
                self.tool_settings.get("pylint", {}).get("init-import"),
            ),
        )

    def apply_shared_defaults(
        self,
        *,
        override: bool = False,
        baseline: SharedKnobSnapshot | None = None,
    ) -> None:
        """Ensure shared configuration defaults are reflected in tool settings."""
        settings = self.tool_settings

        try:
            from .tools.catalog_metadata import catalog_duplicate_preference
        except Exception:  # pragma: no cover - defensive import guard
            duplicate_preference: tuple[str, ...] = ()
        else:
            duplicate_preference = catalog_duplicate_preference()
        if duplicate_preference:
            prefer_list = list(self.dedupe.dedupe_prefer)
            for tool_name in duplicate_preference:
                if tool_name not in prefer_list:
                    prefer_list.append(tool_name)
            self.dedupe.dedupe_prefer = prefer_list

        mypy_settings = settings.setdefault("mypy", {})
        baseline_mypy = _expected_mypy_profile(baseline.type_checking) if baseline is not None else {}

        def set_mypy(key: str, value: object | None) -> None:
            existing = mypy_settings.get(key, UNSET)
            baseline_value = baseline_mypy.get(key, NO_BASELINE)
            if value is None:
                if override:
                    if existing is UNSET:
                        return
                    if baseline_value is not NO_BASELINE and existing != baseline_value:
                        return
                mypy_settings.pop(key, None)
                return
            if override:
                if existing is not UNSET and baseline_value is not NO_BASELINE and existing != baseline_value:
                    return
                mypy_settings[key] = value
            else:
                mypy_settings.setdefault(key, value)

        set_mypy("exclude-gitignore", True)
        set_mypy("sqlite-cache", True)
        set_mypy("show-error-codes", True)
        set_mypy("show-column-numbers", True)

        set_mypy("strict", None)
        set_mypy("warn-redundant-casts", None)
        set_mypy("warn-unused-ignores", None)
        set_mypy("warn-unreachable", None)
        set_mypy("disallow-untyped-decorators", None)
        set_mypy("disallow-any-generics", None)
        set_mypy("check-untyped-defs", None)
        set_mypy("no-implicit-reexport", None)
        set_mypy("ignore-missing-imports", None)



__all__ = [
    "Config",
    "ConfigError",
    "DedupeConfig",
    "ExecutionConfig",
    "FileDiscoveryConfig",
    "OutputConfig",
    "default_parallel_jobs",
]
