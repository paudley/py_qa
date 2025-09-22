"""Lint command implementation."""

from __future__ import annotations

from pathlib import Path
from typing import List

import typer

from ..config import Config, default_parallel_jobs
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
    paths: List[Path] = typer.Argument(
        [], metavar="[PATH]", help="Specific files or directories to lint."
    ),
    root: Path = typer.Option(Path.cwd(), "--root", "-r", help="Project root."),
    changed_only: bool = typer.Option(
        False, help="Limit to files changed according to git."
    ),
    diff_ref: str = typer.Option("HEAD", help="Git ref for change detection."),
    include_untracked: bool = typer.Option(
        True, help="Include untracked files during git discovery."
    ),
    base_branch: str | None = typer.Option(
        None, help="Base branch for merge-base diffing."
    ),
    paths_from_stdin: bool = typer.Option(False, help="Read file paths from stdin."),
    dirs: List[Path] = typer.Option(
        [], "--dir", help="Add directory to discovery roots (repeatable)."
    ),
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
    output_mode: str = typer.Option(
        "concise", "--output", help="Output mode: concise, pretty, or raw."
    ),
    show_passing: bool = typer.Option(
        False, help="Include successful diagnostics in output."
    ),
    report_json: Path | None = typer.Option(
        None, help="Write JSON report to the provided path."
    ),
    sarif_out: Path | None = typer.Option(
        None, help="Write SARIF 2.1.0 report to the provided path."
    ),
    pr_summary_out: Path | None = typer.Option(
        None, help="Write a Markdown PR summary of diagnostics."
    ),
    pr_summary_limit: int = typer.Option(
        100, "--pr-summary-limit", help="Maximum diagnostics in PR summary."
    ),
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
    cache_dir: Path = typer.Option(
        Path(".lint-cache"), "--cache-dir", help="Cache directory for tool results."
    ),
    use_local_linters: bool = typer.Option(
        False,
        "--use-local-linters",
        help="Force vendored linters even if compatible system versions exist.",
    ),
) -> None:
    """Entry point for the ``pyqa lint`` CLI command."""

    if fix_only and check_only:
        raise typer.BadParameter("--fix-only and --check-only are mutually exclusive")
    if verbose and quiet:
        raise typer.BadParameter("--verbose and --quiet cannot be combined")

    effective_jobs = jobs if jobs is not None else default_parallel_jobs()

    options = LintOptions(
        paths=list(paths),
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
    )

    try:
        config = build_config(options)
    except ValueError as exc:  # invalid option combinations
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
