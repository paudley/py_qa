# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Lint command implementation."""

from __future__ import annotations

import os
from pathlib import Path
from typing import List

import typer
from click.core import ParameterSource

from ..config import Config, ConfigError, default_parallel_jobs
from ..discovery import build_default_discovery
from ..execution.orchestrator import Orchestrator
from ..models import RunResult
from ..reporting.emitters import write_json_report, write_pr_summary, write_sarif_report
from ..reporting.formatters import render
from ..tools.registry import DEFAULT_REGISTRY
from .config_builder import build_config
from .options import LintOptions

# pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals


def lint_command(
    ctx: typer.Context,
    paths: List[Path] | None = typer.Argument(None, metavar="[PATH]", help="Specific files or directories to lint."),
    root: Path = typer.Option(Path.cwd(), "--root", "-r", help="Project root."),
    changed_only: bool = typer.Option(False, help="Limit to files changed according to git."),
    diff_ref: str = typer.Option("HEAD", help="Git ref for change detection."),
    include_untracked: bool = typer.Option(True, help="Include untracked files during git discovery."),
    base_branch: str | None = typer.Option(None, help="Base branch for merge-base diffing."),
    paths_from_stdin: bool = typer.Option(False, help="Read file paths from stdin."),
    dirs: List[Path] = typer.Option([], "--dir", help="Add directory to discovery roots (repeatable)."),
    exclude: List[Path] = typer.Option([], help="Exclude specific paths or globs."),
    filters: List[str] = typer.Option(
        [],
        "--filter",
        help="Filter stdout/stderr from TOOL using regex (TOOL:pattern).",
    ),
    only: List[str] = typer.Option([], help="Run only the selected tool(s)."),
    language: List[str] = typer.Option([], help="Filter tools by language."),
    fix_only: bool = typer.Option(False, help="Run only fix-capable actions."),
    check_only: bool = typer.Option(False, help="Run only check actions."),
    verbose: bool = typer.Option(False, help="Verbose output."),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Minimal output."),
    no_color: bool = typer.Option(False, help="Disable ANSI colour output."),
    no_emoji: bool = typer.Option(False, help="Disable emoji output."),
    output_mode: str = typer.Option("concise", "--output", help="Output mode: concise, pretty, or raw."),
    show_passing: bool = typer.Option(False, help="Include successful diagnostics in output."),
    report_json: Path | None = typer.Option(None, help="Write JSON report to the provided path."),
    sarif_out: Path | None = typer.Option(None, help="Write SARIF 2.1.0 report to the provided path."),
    pr_summary_out: Path | None = typer.Option(None, help="Write a Markdown PR summary of diagnostics."),
    pr_summary_limit: int = typer.Option(100, "--pr-summary-limit", help="Maximum diagnostics in PR summary."),
    pr_summary_min_severity: str = typer.Option(
        "warning",
        "--pr-summary-min-severity",
        help="Lowest severity for PR summary (error, warning, notice, note).",
    ),
    pr_summary_template: str = typer.Option(
        "- **{severity}** `{tool}` {message} ({location})",
        "--pr-summary-template",
        help="Custom format string for PR summary entries.",
    ),
    jobs: int | None = typer.Option(
        None,
        "--jobs",
        "-j",
        min=1,
        help="Max parallel jobs (defaults to 75% of available CPU cores).",
    ),
    bail: bool = typer.Option(False, "--bail", help="Exit on first tool failure."),
    no_cache: bool = typer.Option(False, help="Disable on-disk result caching."),
    cache_dir: Path = typer.Option(Path(".lint-cache"), "--cache-dir", help="Cache directory for tool results."),
    use_local_linters: bool = typer.Option(
        False,
        "--use-local-linters",
        help="Force vendored linters even if compatible system versions exist.",
    ),
    strict_config: bool = typer.Option(
        False,
        "--strict-config",
        help="Treat configuration warnings (unknown keys, etc.) as errors.",
    ),
    line_length: int = typer.Option(
        120,
        "--line-length",
        help="Global preferred maximum line length applied to supported tools.",
    ),
    sql_dialect: str = typer.Option(
        "postgresql",
        "--sql-dialect",
        help="Default SQL dialect for dialect-aware tools (e.g. sqlfluff).",
    ),
) -> None:
    """Entry point for the ``pyqa lint`` CLI command."""

    if fix_only and check_only:
        raise typer.BadParameter("--fix-only and --check-only are mutually exclusive")
    if verbose and quiet:
        raise typer.BadParameter("--verbose and --quiet cannot be combined")

    invocation_cwd = Path.cwd()
    provided_paths = list(paths or [])
    normalized_paths = [_normalise_path(arg, invocation_cwd) for arg in provided_paths]

    root_source = ctx.get_parameter_source("root")
    root = _normalise_path(root, invocation_cwd)
    if root_source in (ParameterSource.DEFAULT, ParameterSource.DEFAULT_MAP) and normalized_paths:
        derived_root = _derive_default_root(normalized_paths)
        if derived_root is not None:
            root = derived_root

    effective_jobs = jobs if jobs is not None else default_parallel_jobs()

    provided = _collect_provided_flags(
        ctx,
        paths_provided=bool(normalized_paths),
        dirs=dirs,
        exclude=exclude,
        filters=filters,
        only=only,
        language=language,
    )

    options = LintOptions(
        paths=list(normalized_paths),
        root=root,
        changed_only=changed_only,
        diff_ref=diff_ref,
        include_untracked=include_untracked,
        base_branch=base_branch,
        paths_from_stdin=paths_from_stdin,
        dirs=list(dirs),
        exclude=list(exclude),
        filters=list(filters),
        only=list(only),
        language=list(language),
        fix_only=fix_only,
        check_only=check_only,
        verbose=verbose,
        quiet=quiet,
        no_color=no_color,
        no_emoji=no_emoji,
        output_mode=output_mode,
        show_passing=show_passing,
        jobs=effective_jobs,
        bail=bail,
        no_cache=no_cache,
        cache_dir=cache_dir,
        pr_summary_out=pr_summary_out,
        pr_summary_limit=pr_summary_limit,
        pr_summary_min_severity=pr_summary_min_severity,
        pr_summary_template=pr_summary_template,
        use_local_linters=use_local_linters,
        strict_config=strict_config,
        line_length=line_length,
        sql_dialect=sql_dialect,
        provided=provided,
    )

    try:
        config = build_config(options)
    except (ValueError, ConfigError) as exc:  # invalid option combinations
        raise typer.BadParameter(str(exc)) from exc
    orchestrator = Orchestrator(
        registry=DEFAULT_REGISTRY,
        discovery=build_default_discovery(),
    )
    result = orchestrator.run(config, root=root)
    _handle_reporting(
        result,
        config,
        report_json,
        sarif_out,
        pr_summary_out,
    )
    raise typer.Exit(code=1 if result.failed else 0)


def _handle_reporting(
    result: RunResult,
    config: Config,
    report_json: Path | None,
    sarif_out: Path | None,
    pr_summary_out: Path | None,
) -> None:
    render(result, config.output)
    if report_json:
        write_json_report(result, report_json)
    if sarif_out:
        write_sarif_report(result, sarif_out)
    if pr_summary_out:
        write_pr_summary(
            result,
            pr_summary_out,
            limit=config.output.pr_summary_limit,
            min_severity=config.output.pr_summary_min_severity,
            template=config.output.pr_summary_template,
        )


def _collect_provided_flags(
    ctx: typer.Context,
    *,
    paths_provided: bool,
    dirs: List[Path],
    exclude: List[Path],
    filters: List[str],
    only: List[str],
    language: List[str],
) -> set[str]:
    tracked = {
        "changed_only",
        "diff_ref",
        "include_untracked",
        "base_branch",
        "paths_from_stdin",
        "dirs",
        "exclude",
        "filters",
        "only",
        "language",
        "fix_only",
        "check_only",
        "verbose",
        "quiet",
        "no_color",
        "no_emoji",
        "output_mode",
        "show_passing",
        "jobs",
        "bail",
        "no_cache",
        "cache_dir",
        "pr_summary_out",
        "pr_summary_limit",
        "pr_summary_min_severity",
        "pr_summary_template",
        "use_local_linters",
        "line_length",
        "sql_dialect",
    }
    provided: set[str] = set()
    for name in tracked:
        source = ctx.get_parameter_source(name)
        if source not in (ParameterSource.DEFAULT, ParameterSource.DEFAULT_MAP):
            provided.add(name)
    if paths_provided:
        provided.add("paths")
    if dirs:
        provided.add("dirs")
    if exclude:
        provided.add("exclude")
    if filters:
        provided.add("filters")
    if only:
        provided.add("only")
    if language:
        provided.add("language")
    return provided


def _normalise_path(value: Path, cwd: Path) -> Path:
    candidate = value if value.is_absolute() else cwd / value
    return candidate.resolve()


def _derive_default_root(paths: List[Path]) -> Path | None:
    if not paths:
        return None
    candidates = [path if path.is_dir() else path.parent for path in paths]
    if not candidates:
        return None
    common = Path(os.path.commonpath([str(candidate) for candidate in candidates]))
    return common.resolve()
