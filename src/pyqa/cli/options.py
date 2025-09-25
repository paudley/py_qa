# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Data structures for lint command options."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class LintOptions:
    """Container for CLI options passed to the lint command."""

    paths: list[Path]
    root: Path
    changed_only: bool
    diff_ref: str
    include_untracked: bool
    base_branch: str | None
    paths_from_stdin: bool
    dirs: list[Path] = field(default_factory=list)
    exclude: list[Path] = field(default_factory=list)
    filters: list[str] = field(default_factory=list)
    only: list[str] = field(default_factory=list)
    language: list[str] = field(default_factory=list)
    fix_only: bool = False
    check_only: bool = False
    verbose: bool = False
    quiet: bool = False
    no_color: bool = False
    no_emoji: bool = False
    no_stats: bool = False
    output_mode: str = "concise"
    show_passing: bool = False
    jobs: int = 1
    bail: bool = False
    no_cache: bool = False
    cache_dir: Path = Path(".lint-cache")
    pr_summary_out: Path | None = None
    pr_summary_limit: int = 100
    pr_summary_min_severity: str = "warning"
    pr_summary_template: str = "- **{severity}** `{tool}` {message} ({location})"
    use_local_linters: bool = False
    strict_config: bool = False
    provided: set[str] = field(default_factory=set)
    line_length: int = 120
    sql_dialect: str = "postgresql"
    python_version: str | None = None
    max_complexity: int | None = None
    max_arguments: int | None = None
    type_checking: str | None = None
    bandit_severity: str | None = None
    bandit_confidence: str | None = None
    pylint_fail_under: float | None = None
    sensitivity: str | None = None
    advice: bool = False


@dataclass(slots=True)
class InstallOptions:
    """Options controlling installation of managed tools."""

    include_optional: bool = True
    generate_stubs: bool = True


ToolFilters = dict[str, list[str]]
