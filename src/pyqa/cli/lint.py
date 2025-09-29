# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Lint command implementation."""

from __future__ import annotations

import os
from pathlib import Path
from threading import Lock

import typer
from rich import box
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table
from rich.text import Text

from ..config import Config, ConfigError, default_parallel_jobs
from ..console import console_manager, is_tty
from ..constants import PY_QA_DIR_NAME
from ..discovery import build_default_discovery
from ..execution.orchestrator import FetchEvent, Orchestrator, OrchestratorHooks
from ..logging import info, warn
from ..models import RunResult
from ..reporting.emitters import write_json_report, write_pr_summary, write_sarif_report
from ..reporting.formatters import render
from ..tool_env.models import PreparedCommand
from ..tooling.loader import CatalogIntegrityError, CatalogValidationError, ToolCatalogLoader
from ..tools.builtin_registry import initialize_registry
from ..tools.registry import DEFAULT_REGISTRY
from ..workspace import is_py_qa_workspace
from .config_builder import build_config
from .doctor import run_doctor
from .options import LintOptions
from .tool_info import run_tool_info
from .utils import filter_py_qa_paths

PHASE_SORT_ORDER: tuple[str, ...] = (
    "lint",
    "format",
    "analysis",
    "security",
    "test",
    "coverage",
    "utility",
)


def lint_command(
    ctx: typer.Context,
    paths: list[Path] | None = typer.Argument(
        None,
        metavar="[PATH]",
        help="Specific files or directories to lint.",
    ),
    root: Path = typer.Option(Path.cwd(), "--root", "-r", help="Project root."),
    changed_only: bool = typer.Option(False, help="Limit to files changed according to git."),
    diff_ref: str = typer.Option("HEAD", help="Git ref for change detection."),
    include_untracked: bool = typer.Option(
        True,
        help="Include untracked files during git discovery.",
    ),
    base_branch: str | None = typer.Option(None, help="Base branch for merge-base diffing."),
    paths_from_stdin: bool = typer.Option(False, help="Read file paths from stdin."),
    dirs: list[Path] = typer.Option(
        [],
        "--dir",
        help="Add directory to discovery roots (repeatable).",
    ),
    exclude: list[Path] = typer.Option([], help="Exclude specific paths or globs."),
    filters: list[str] = typer.Option(
        [],
        "--filter",
        help="Filter stdout/stderr from TOOL using regex (TOOL:pattern).",
    ),
    only: list[str] = typer.Option([], help="Run only the selected tool(s)."),
    language: list[str] = typer.Option([], help="Filter tools by language."),
    fix_only: bool = typer.Option(False, help="Run only fix-capable actions."),
    check_only: bool = typer.Option(False, help="Run only check actions."),
    verbose: bool = typer.Option(False, help="Verbose output."),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Minimal output."),
    no_color: bool = typer.Option(False, help="Disable ANSI colour output."),
    no_emoji: bool = typer.Option(False, help="Disable emoji output."),
    output_mode: str = typer.Option(
        "concise",
        "--output",
        help="Output mode: concise, pretty, or raw.",
    ),
    show_passing: bool = typer.Option(False, help="Include successful diagnostics in output."),
    no_stats: bool = typer.Option(False, help="Suppress summary statistics."),
    report_json: Path | None = typer.Option(None, help="Write JSON report to the provided path."),
    sarif_out: Path | None = typer.Option(
        None,
        help="Write SARIF 2.1.0 report to the provided path.",
    ),
    pr_summary_out: Path | None = typer.Option(
        None,
        help="Write a Markdown PR summary of diagnostics.",
    ),
    pr_summary_limit: int = typer.Option(
        100,
        "--pr-summary-limit",
        help="Maximum diagnostics in PR summary.",
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
        Path(".lint-cache"),
        "--cache-dir",
        help="Cache directory for tool results.",
    ),
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
    max_complexity: int | None = typer.Option(
        None,
        "--max-complexity",
        min=1,
        help="Override maximum cyclomatic complexity shared across supported tools.",
    ),
    max_arguments: int | None = typer.Option(
        None,
        "--max-arguments",
        min=1,
        help="Override maximum function arguments shared across supported tools.",
    ),
    type_checking: str | None = typer.Option(
        None,
        "--type-checking",
        case_sensitive=False,
        help="Override type-checking strictness (lenient, standard, or strict).",
    ),
    bandit_severity: str | None = typer.Option(
        None,
        "--bandit-severity",
        case_sensitive=False,
        help="Override Bandit's minimum severity (low, medium, high).",
    ),
    bandit_confidence: str | None = typer.Option(
        None,
        "--bandit-confidence",
        case_sensitive=False,
        help="Override Bandit's minimum confidence (low, medium, high).",
    ),
    pylint_fail_under: float | None = typer.Option(
        None,
        "--pylint-fail-under",
        help="Override pylint fail-under score (0-10).",
    ),
    sensitivity: str | None = typer.Option(
        None,
        "--sensitivity",
        case_sensitive=False,
        help="Overall sensitivity (low, medium, high, maximum) to cascade severity tweaks.",
    ),
    sql_dialect: str = typer.Option(
        "postgresql",
        "--sql-dialect",
        help="Default SQL dialect for dialect-aware tools (e.g. sqlfluff).",
    ),
    doctor: bool = typer.Option(False, "--doctor", help="Run environment diagnostics and exit."),
    tool_info: str | None = typer.Option(
        None,
        "--tool-info",
        metavar="TOOL",
        help="Display detailed information for TOOL and exit.",
    ),
    fetch_all_tools: bool = typer.Option(
        False,
        "--fetch-all-tools",
        help="Download or prepare runtimes for every registered tool and exit.",
    ),
    advice: bool = typer.Option(
        False,
        "--advice",
        help="Provide SOLID-aligned refactoring suggestions alongside diagnostics.",
    ),
) -> None:
    """Entry point for the ``pyqa lint`` CLI command."""
    if doctor and tool_info:
        raise typer.BadParameter("--doctor and --tool-info cannot be combined")
    if doctor and fetch_all_tools:
        raise typer.BadParameter("--doctor and --fetch-all-tools cannot be combined")
    if tool_info and fetch_all_tools:
        raise typer.BadParameter("--tool-info and --fetch-all-tools cannot be combined")

    if fix_only and check_only:
        raise typer.BadParameter("--fix-only and --check-only are mutually exclusive")
    if verbose and quiet:
        raise typer.BadParameter("--verbose and --quiet cannot be combined")

    invocation_cwd = Path.cwd()
    provided_paths = list(paths or [])
    normalized_paths = [_normalise_path(arg, invocation_cwd) for arg in provided_paths]

    root_source = _parameter_source_name(ctx, "root")
    root = _normalise_path(root, invocation_cwd)
    if root_source in {"DEFAULT", "DEFAULT_MAP"} and normalized_paths:
        derived_root = _derive_default_root(normalized_paths)
        if derived_root is not None:
            root = derived_root

    is_py_qa_root = is_py_qa_workspace(root)
    ignored_py_qa: list[str] = []
    if not is_py_qa_root and normalized_paths:
        normalized_paths, ignored_py_qa = filter_py_qa_paths(normalized_paths, root)
        if ignored_py_qa:
            unique = ", ".join(dict.fromkeys(ignored_py_qa))
            warn(
                (
                    f"Ignoring path(s) {unique}: '{PY_QA_DIR_NAME}' directories are skipped "
                    "unless lint runs inside the py_qa workspace."
                ),
                use_emoji=not no_emoji,
            )

    if doctor:
        exit_code = run_doctor(root)
        raise typer.Exit(code=exit_code)

    effective_jobs = jobs if jobs is not None else default_parallel_jobs()

    if type_checking is not None:
        normalized_strictness = type_checking.lower()
        if normalized_strictness not in {"lenient", "standard", "strict"}:
            raise typer.BadParameter("--type-checking must be one of: lenient, standard, strict")
        type_checking = normalized_strictness

    def _normalise_bandit(value: str | None, option: str) -> str | None:
        if value is None:
            return None
        normalized = value.lower()
        if normalized not in {"low", "medium", "high"}:
            raise typer.BadParameter(f"{option} must be one of: low, medium, high")
        return normalized

    bandit_severity = _normalise_bandit(bandit_severity, "--bandit-severity")
    bandit_confidence = _normalise_bandit(bandit_confidence, "--bandit-confidence")

    if pylint_fail_under is not None and not (0 <= pylint_fail_under <= 10):
        raise typer.BadParameter("--pylint-fail-under must be between 0 and 10")

    if sensitivity is not None:
        sensitivity_normalized = sensitivity.lower()
        if sensitivity_normalized not in {"low", "medium", "high", "maximum"}:
            raise typer.BadParameter("--sensitivity must be one of: low, medium, high, maximum")
        sensitivity = sensitivity_normalized

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
        no_stats=no_stats,
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
        max_complexity=max_complexity,
        max_arguments=max_arguments,
        type_checking=type_checking,
        bandit_severity=bandit_severity,
        bandit_confidence=bandit_confidence,
        pylint_fail_under=pylint_fail_under,
        sensitivity=sensitivity,
        advice=advice,
        provided=provided,
    )

    try:
        config = build_config(options)
    except (ValueError, ConfigError) as exc:  # invalid option combinations
        raise typer.BadParameter(str(exc)) from exc

    catalog_snapshot = initialize_registry(registry=DEFAULT_REGISTRY)

    hooks = OrchestratorHooks()
    orchestrator = Orchestrator(
        registry=DEFAULT_REGISTRY,
        discovery=build_default_discovery(),
        hooks=hooks,
    )

    if tool_info:
        exit_code = run_tool_info(
            tool_info,
            root=root,
            cfg=config,
            catalog_snapshot=catalog_snapshot,
        )
        raise typer.Exit(code=exit_code)
    if fetch_all_tools:
        total_actions = sum(len(tool.actions) for tool in DEFAULT_REGISTRY.tools())
        progress_enabled = total_actions > 0 and not quiet and config.output.color and is_tty()
        console = console_manager.get(color=config.output.color, emoji=config.output.emoji)
        results: list[tuple[str, str, PreparedCommand | None, str | None]]

        if progress_enabled:
            progress = Progress(
                SpinnerColumn(),
                TextColumn("{task.description}"),
                BarColumn(bar_width=None),
                TimeElapsedColumn(),
                console=console,
                transient=not verbose,
            )
            task_id = progress.add_task("Preparing tools", total=total_actions)

            def progress_callback(
                event: FetchEvent,
                tool_name: str,
                action_name: str,
                index: int,
                total: int,
                message: str | None,
            ) -> None:
                description = f"{tool_name}:{action_name}"
                if event == "start":
                    status = "Preparing"
                    completed = index - 1
                elif event == "completed":
                    status = "Prepared"
                    completed = index
                else:
                    status = "Error"
                    completed = index
                    if message and verbose:
                        console.print(f"[red]{description} failed: {message}[/red]")
                progress.update(
                    task_id,
                    completed=completed,
                    total=total,
                    description=f"{status} {description}",
                )

            with progress:
                results = orchestrator.fetch_all_tools(
                    config,
                    root=root,
                    callback=progress_callback,
                )
        else:
            results = orchestrator.fetch_all_tools(config, root=root)
        tool_lookup = {tool.name: tool for tool in DEFAULT_REGISTRY.tools()}
        phase_rank = {
            name: PHASE_SORT_ORDER.index(tool.phase) if tool.phase in PHASE_SORT_ORDER else len(PHASE_SORT_ORDER)
            for name, tool in tool_lookup.items()
        }
        results.sort(
            key=lambda item: (
                phase_rank.get(item[0], len(PHASE_SORT_ORDER)),
                item[0],
                item[1],
            ),
        )

        if not quiet:
            table = Table(
                title="Tool Preparation",
                box=box.ROUNDED,
                show_header=True,
                header_style="bold" if config.output.color else None,
            )
            table.add_column("Tool", style="cyan" if config.output.color else None)
            table.add_column("Action", style="cyan" if config.output.color else None)
            table.add_column("Phase", style="cyan" if config.output.color else None)
            table.add_column("Status", style="magenta" if config.output.color else None)
            table.add_column("Source", style="magenta" if config.output.color else None)
            table.add_column("Version", style="green" if config.output.color else None)
            failures: list[tuple[str, str, str]] = []
            for tool_name, action_name, prepared, error in results:
                phase = getattr(tool_lookup.get(tool_name), "phase", "-")
                if prepared is None:
                    status = "error"
                    source = "-"
                    version = "-"
                    failures.append((tool_name, action_name, error or "unknown error"))
                else:
                    status = "ready"
                    source = prepared.source
                    version = prepared.version or "unknown"
                table.add_row(tool_name, action_name, phase, status, source, version)
            console.print(table)
            info(
                f"Prepared {len(results)} tool action(s) without execution.",
                use_emoji=config.output.emoji,
                use_color=config.output.color,
            )
            for tool_name, action_name, message in failures:
                warn(
                    f"Failed to prepare {tool_name}:{action_name} — {message}",
                    use_emoji=config.output.emoji,
                    use_color=config.output.color,
                )
        raise typer.Exit(code=0)
    progress_enabled = (
        config.output.output == "concise" and not quiet and not config.output.quiet and config.output.color and is_tty()
    )

    extra_phases = 2  # post-processing + rendering
    progress: Progress | None = None
    progress_task_id: int | None = None
    progress_lock = Lock()
    progress_console = None
    progress_total = extra_phases
    progress_completed = 0
    progress_started = False

    if progress_enabled:
        console = console_manager.get(color=config.output.color, emoji=config.output.emoji)
        progress_console = console
        console_width = getattr(console.size, "width", 100)
        reserved_columns = 40
        bar_available = max(10, console_width - reserved_columns)
        bar_width = max(20, int(bar_available * 0.8))

        progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(bar_width=bar_width),
            TextColumn("{task.completed}/{task.total}"),
            TimeElapsedColumn(),
            TextColumn("{task.fields[current_status]}", justify="right"),
            console=console,
            transient=True,
        )
        progress_task_id = progress.add_task(
            "Linting",
            total=progress_total,
            current_status="[cyan]waiting[/]" if config.output.color else "waiting",
        )

        def ensure_started() -> None:
            nonlocal progress_started
            if progress is None or progress_started:
                return
            progress.start()
            progress_started = True

        def before_tool(tool_name: str) -> None:
            if progress is None or progress_task_id is None:
                return
            with progress_lock:
                ensure_started()
                progress.update(
                    progress_task_id,
                    description=f"Linting {tool_name}",
                    current_status="[cyan]running[/]" if config.output.color else "running",
                )

        def after_tool(outcome) -> None:  # noqa: ANN001
            if progress is None or progress_task_id is None:
                return
            nonlocal progress_completed
            status = "[green]ok[/]" if outcome.ok and config.output.color else ("ok" if outcome.ok else "issues")
            if not outcome.ok and config.output.color:
                status = "[red]issues[/]"
            label = f"{outcome.tool}:{outcome.action}"
            with progress_lock:
                ensure_started()
                progress.advance(progress_task_id, advance=1)
                progress_completed += 1
                progress.update(
                    progress_task_id,
                    current_status=f"{label} {status}",
                )

        def after_discovery(file_count: int) -> None:
            if progress is None or progress_task_id is None:
                return
            with progress_lock:
                ensure_started()
                status = "[cyan]queued[/]" if config.output.color else "queued"
                progress.update(
                    progress_task_id,
                    description=f"Linting ({file_count} files)",
                    current_status=status,
                )

        def after_execution_hook(_result: RunResult) -> None:
            if progress is None or progress_task_id is None:
                return
            nonlocal progress_completed
            with progress_lock:
                ensure_started()
                progress.advance(progress_task_id, advance=1)
                progress_completed += 1
                status = "[cyan]post-processing[/]" if config.output.color else "post-processing"
                progress.update(
                    progress_task_id,
                    current_status=status,
                )

        def advance_rendering_phase() -> None:
            if progress is None or progress_task_id is None:
                return
            nonlocal progress_completed
            with progress_lock:
                ensure_started()
                progress.advance(progress_task_id, advance=1)
                progress_completed += 1
                status = "[cyan]rendering output[/]" if config.output.color else "rendering output"
                progress.update(
                    progress_task_id,
                    current_status=status,
                )

        hooks.before_tool = before_tool
        hooks.after_tool = after_tool
        hooks.after_discovery = after_discovery
        hooks.after_execution = after_execution_hook

        def after_plan_hook(total_actions: int) -> None:
            if progress is None or progress_task_id is None:
                return
            nonlocal progress_total
            with progress_lock:
                ensure_started()
                progress_total = total_actions + extra_phases
                progress.update(progress_task_id, total=progress_total)

        hooks.after_plan = after_plan_hook

    def _finalise_progress(success: bool) -> Text | None:
        if progress is None or progress_task_id is None:
            return None
        summary = "Linting complete" if success else "Linting halted"
        status_text = (
            "[green]done[/]"
            if success and config.output.color
            else ("[red]issues detected[/]" if config.output.color else ("done" if success else "issues detected"))
        )
        with progress_lock:
            total = max(progress_total, progress_completed)
            progress.update(
                progress_task_id,
                total=total,
                description=summary,
                current_status=status_text,
            )
        if config.output.color:
            return Text(summary, style="green" if success else "red")
        return Text(summary)

    final_summary: Text | None = None
    if progress is not None:
        result = orchestrator.run(config, root=root)
        advance_rendering_phase()
        final_summary = _finalise_progress(not result.failed)
        if progress_started:
            progress.stop()
    else:
        result = orchestrator.run(config, root=root)

    if final_summary and progress_console is not None:
        progress_console.print(final_summary)
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
    dirs: list[Path],
    exclude: list[Path],
    filters: list[str],
    only: list[str],
    language: list[str],
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
        "no_stats",
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
        "max_complexity",
        "max_arguments",
        "type_checking",
        "bandit_severity",
        "bandit_confidence",
        "pylint_fail_under",
        "sensitivity",
        "sql_dialect",
        "advice",
    }
    provided: set[str] = set()
    for name in tracked:
        source = _parameter_source_name(ctx, name)
        if source not in {"DEFAULT", "DEFAULT_MAP", None}:
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


def _display_path(path: Path, root: Path) -> str:
    try:
        relative = path.relative_to(root)
        return relative.as_posix()
    except ValueError:
        return str(path)


def _derive_default_root(paths: list[Path]) -> Path | None:
    if not paths:
        return None
    candidates = [path if path.is_dir() else path.parent for path in paths]
    if not candidates:
        return None
    common = Path(os.path.commonpath([str(candidate) for candidate in candidates]))
    return common.resolve()


def _parameter_source_name(ctx: typer.Context, name: str) -> str | None:
    getter = getattr(ctx, "get_parameter_source", None)
    if not callable(getter):
        return None
    try:
        source = getter(name)
    except TypeError:
        return None
    if source is None:
        return None
    label = getattr(source, "name", None)
    return label if isinstance(label, str) else str(source)
