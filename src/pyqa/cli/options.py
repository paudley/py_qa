# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Data structures for lint command options."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List


# pylint: disable=too-many-instance-attributes
@dataclass(slots=True)
class LintOptions:
    """Container for CLI options passed to the lint command."""

    paths: List[Path]
    root: Path
    changed_only: bool
    diff_ref: str
    include_untracked: bool
    base_branch: str | None
    paths_from_stdin: bool
    dirs: List[Path] = field(default_factory=list)
    exclude: List[Path] = field(default_factory=list)
    filters: List[str] = field(default_factory=list)
    only: List[str] = field(default_factory=list)
    language: List[str] = field(default_factory=list)
    fix_only: bool = False
    check_only: bool = False
    verbose: bool = False
    quiet: bool = False
    no_color: bool = False
    no_emoji: bool = False
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


@dataclass(slots=True)
class InstallOptions:
    """Options controlling installation of managed tools."""

    include_optional: bool = True
    generate_stubs: bool = True


ToolFilters = Dict[str, List[str]]
