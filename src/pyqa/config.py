# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Configuration models and helpers for the pyqa lint orchestration package."""

from __future__ import annotations

import math
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal


class ConfigError(Exception):
    """Raised when configuration input is invalid."""


# pylint: disable=too-many-instance-attributes
def default_parallel_jobs() -> int:
    """Return 75% of available CPU cores (minimum of 1)."""

    cores = os.cpu_count() or 1
    proposed = max(1, math.floor(cores * 0.75))
    return proposed


@dataclass(slots=True)
class FileDiscoveryConfig:
    """Configuration for how to discover and filter files within a project."""

    roots: list[Path] = field(default_factory=lambda: [Path(".")])
    excludes: list[Path] = field(default_factory=list)
    paths_from_stdin: bool = False
    changed_only: bool = False
    diff_ref: str = "HEAD"
    include_untracked: bool = True
    base_branch: str | None = None
    pre_commit: bool = False
    respect_gitignore: bool = False
    explicit_files: list[Path] = field(default_factory=list)


# pylint: disable=too-many-instance-attributes
@dataclass(slots=True)
class OutputConfig:
    """Configuration for controlling output, reporting, and artifact creation."""

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
    tool_filters: dict[str, list[str]] = field(default_factory=dict)


# pylint: disable=too-many-instance-attributes
@dataclass(slots=True)
class ExecutionConfig:
    """Execution behaviour and lint tool selection configuration."""

    only: list[str] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)
    enable: list[str] = field(default_factory=list)
    strict: bool = False
    jobs: int = field(default_factory=default_parallel_jobs)
    fix_only: bool = False
    check_only: bool = False
    force_all: bool = False
    respect_config: bool = False
    cache_enabled: bool = True
    cache_dir: Path = field(default_factory=lambda: Path(".lint-cache"))
    bail: bool = False
    use_local_linters: bool = False


@dataclass(slots=True)
class DedupeConfig:
    """Configuration knobs for deduplicating diagnostics."""

    dedupe: bool = False
    dedupe_by: Literal["first", "severity", "prefer"] = "first"
    dedupe_prefer: list[str] = field(default_factory=list)
    dedupe_line_fuzz: int = 2
    dedupe_same_file_only: bool = True


DEFAULT_QUALITY_CHECKS: list[str] = ["license", "file-size", "schema", "python"]
DEFAULT_SCHEMA_TARGETS = [Path("ref_docs/tool-schema.json")]
DEFAULT_PROTECTED_BRANCHES = ["main", "master"]

DEFAULT_CLEAN_PATTERNS: list[str] = [
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

DEFAULT_CLEAN_TREES: list[str] = ["examples", "packages", "build"]

DEFAULT_UPDATE_SKIP_PATTERNS: list[str] = ["pyreadstat", ".git/modules"]


@dataclass(slots=True)
class LicenseConfig:
    """Project-wide licensing policy configuration."""

    spdx: str | None = None
    notice: str | None = None
    copyright: str | None = None
    year: str | None = None
    require_spdx: bool = True
    require_notice: bool = True
    allow_alternate_spdx: list[str] = field(default_factory=list)
    exceptions: list[str] = field(default_factory=list)


@dataclass(slots=True)
class QualityConfigSection:
    """Quality enforcement configuration shared across commands."""

    checks: list[str] = field(default_factory=lambda: list(DEFAULT_QUALITY_CHECKS))
    skip_globs: list[str] = field(default_factory=list)
    schema_targets: list[Path] = field(default_factory=lambda: list(DEFAULT_SCHEMA_TARGETS))
    warn_file_size: int = 5 * 1024 * 1024
    max_file_size: int = 10 * 1024 * 1024
    protected_branches: list[str] = field(default_factory=lambda: list(DEFAULT_PROTECTED_BRANCHES))


@dataclass(slots=True)
class CleanConfig:
    """Configuration for repository cleanup patterns."""

    patterns: list[str] = field(default_factory=lambda: list(DEFAULT_CLEAN_PATTERNS))
    trees: list[str] = field(default_factory=lambda: list(DEFAULT_CLEAN_TREES))


@dataclass(slots=True)
class UpdateConfig:
    """Configuration for workspace dependency updates."""

    skip_patterns: list[str] = field(default_factory=lambda: list(DEFAULT_UPDATE_SKIP_PATTERNS))
    enabled_managers: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Config:
    """Primary configuration container used by the orchestrator."""

    file_discovery: FileDiscoveryConfig = field(default_factory=FileDiscoveryConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    dedupe: DedupeConfig = field(default_factory=DedupeConfig)
    severity_rules: list[str] = field(default_factory=list)
    tool_settings: dict[str, dict[str, object]] = field(default_factory=dict)
    license: LicenseConfig = field(default_factory=LicenseConfig)
    quality: QualityConfigSection = field(default_factory=QualityConfigSection)
    clean: CleanConfig = field(default_factory=CleanConfig)
    update: UpdateConfig = field(default_factory=UpdateConfig)

    def to_dict(self) -> dict[str, object]:
        """Return a dictionary representation suitable for serialization."""

        return {
            "file_discovery": asdict(self.file_discovery),
            "output": asdict(self.output),
            "execution": asdict(self.execution),
            "dedupe": asdict(self.dedupe),
            "severity_rules": list(self.severity_rules),
            "tools": {
                tool: dict(settings) for tool, settings in self.tool_settings.items()
            },
            "license": asdict(self.license),
            "quality": {
                **asdict(self.quality),
                "schema_targets": [str(path) for path in self.quality.schema_targets],
            },
            "clean": asdict(self.clean),
            "update": asdict(self.update),
        }
