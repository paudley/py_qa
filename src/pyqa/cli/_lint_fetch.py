# SPDX-License-Identifier: MIT
"""Helpers for rendering fetch-all-tools output in the CLI."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich import box
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table

from ..console import console_manager, is_tty
from ..logging import info, warn
from ..tool_env.models import PreparedCommand
from ..tools.registry import DEFAULT_REGISTRY

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from .lint import LintRuntimeContext

FetchResult = list[tuple[str, str, PreparedCommand | None, str | None]]


def render_fetch_all_tools(
    runtime: "LintRuntimeContext",
    *,
    phase_order: tuple[str, ...],
) -> int:
    """Fetch tool runtimes, emit a summary table, and return the exit status."""

    config = runtime.config
    state = runtime.state
    total_actions = sum(len(tool.actions) for tool in DEFAULT_REGISTRY.tools())
    progress_enabled = (
        total_actions > 0 and not state.display.quiet and config.output.color and is_tty()
    )
    console = console_manager.get(color=config.output.color, emoji=config.output.emoji)
    verbose = state.display.verbose

    if progress_enabled:
        results = _fetch_with_progress(runtime, total_actions, console, verbose)
    else:
        results = runtime.orchestrator.fetch_all_tools(config, root=runtime.state.root)

    _render_fetch_summary(console, config, state, results, phase_order)
    return 0


def _fetch_with_progress(
    runtime: "LintRuntimeContext",
    total_actions: int,
    console,
    verbose: bool,
) -> FetchResult:
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
        event,
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
        results = runtime.orchestrator.fetch_all_tools(
            runtime.config,
            root=runtime.state.root,
            callback=progress_callback,
        )
    return results


def _render_fetch_summary(
    console,
    config,
    state,
    results: FetchResult,
    phase_order: tuple[str, ...],
) -> None:
    tool_lookup = {tool.name: tool for tool in DEFAULT_REGISTRY.tools()}
    phase_rank = {
        name: (
            phase_order.index(tool.phase)
            if tool.phase in phase_order
            else len(phase_order)
        )
        for name, tool in tool_lookup.items()
    }
    results.sort(
        key=lambda item: (
            phase_rank.get(item[0], len(phase_order)),
            item[0],
            item[1],
        ),
    )

    if state.display.quiet:
        return

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
