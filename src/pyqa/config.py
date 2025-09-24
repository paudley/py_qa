# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Configuration models and helpers for the pyqa lint orchestration package."""

from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Final, Literal, cast

from pydantic import BaseModel, ConfigDict, Field


class ConfigError(Exception):
    """Raised when configuration input is invalid."""


def default_parallel_jobs() -> int:
    """Return 75% of available CPU cores (minimum of 1)."""

    cores = os.cpu_count() or 1
    proposed = max(1, math.floor(cores * 0.75))
    return proposed


class FileDiscoveryConfig(BaseModel):
    """Configuration for how to discover and filter files within a project."""

    model_config = ConfigDict(validate_assignment=True)

    roots: list[Path] = Field(default_factory=lambda: [Path(".")])
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
    schema_targets: list[Path] = Field(
        default_factory=lambda: list(DEFAULT_SCHEMA_TARGETS)
    )
    warn_file_size: int = 5 * 1024 * 1024
    max_file_size: int = 10 * 1024 * 1024
    protected_branches: list[str] = Field(
        default_factory=lambda: list(DEFAULT_PROTECTED_BRANCHES)
    )


class CleanConfig(BaseModel):
    """Configuration for repository cleanup patterns."""

    model_config = ConfigDict(validate_assignment=True)

    patterns: list[str] = Field(default_factory=lambda: list(DEFAULT_CLEAN_PATTERNS))
    trees: list[str] = Field(default_factory=lambda: list(DEFAULT_CLEAN_TREES))


class UpdateConfig(BaseModel):
    """Configuration for workspace dependency updates."""

    model_config = ConfigDict(validate_assignment=True)

    skip_patterns: list[str] = Field(
        default_factory=lambda: list(DEFAULT_UPDATE_SKIP_PATTERNS)
    )
    enabled_managers: list[str] = Field(default_factory=list)


class Config(BaseModel):
    """Primary configuration container used by the orchestrator."""

    model_config = ConfigDict(validate_assignment=True)

    file_discovery: FileDiscoveryConfig = Field(default_factory=FileDiscoveryConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)
    dedupe: DedupeConfig = Field(default_factory=DedupeConfig)
    severity_rules: list[str] = Field(default_factory=list)
    tool_settings: dict[str, dict[str, object]] = Field(default_factory=dict)
    license: LicenseConfig = Field(default_factory=LicenseConfig)
    quality: QualityConfigSection = Field(default_factory=QualityConfigSection)
    clean: CleanConfig = Field(default_factory=CleanConfig)
    update: UpdateConfig = Field(default_factory=UpdateConfig)

    def to_dict(self) -> dict[str, object]:
        """Return a dictionary representation suitable for serialization."""

        payload: dict[str, object] = dict(self.model_dump(mode="python"))
        payload["severity_rules"] = list(self.severity_rules)
        quality_cfg = cast(QualityConfigSection, self.quality)
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


__all__ = [
    "Config",
    "ConfigError",
    "DedupeConfig",
    "ExecutionConfig",
    "FileDiscoveryConfig",
    "OutputConfig",
    "default_parallel_jobs",
]
