# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Helpers for rendering fetch-all-tools output in the CLI."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Literal, cast

from rich import box
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table

from pyqa.core.environment.tool_env.models import PreparedCommand
from pyqa.runtime.console.manager import detect_tty, get_console_manager

from ....config import Config
from ....tools.base import Tool
from ....tools.registry import DEFAULT_REGISTRY
from .preparation import PreparedLintState

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from .runtime import LintRuntimeContext

FetchResult = list[tuple[str, str, PreparedCommand | None, str | None]]
ProgressEventLiteral = Literal["start", "completed", "error"]
EVENT_START: Final[ProgressEventLiteral] = "start"
EVENT_COMPLETED: Final[ProgressEventLiteral] = "completed"
EVENT_ERROR: Final[ProgressEventLiteral] = "error"
PROGRESS_PAYLOAD_SIZE: Final[int] = 6


@dataclass(frozen=True, slots=True)
class _FetchProgressRecord:
    """Structured representation of a tool preparation progress event."""

    event: ProgressEventLiteral
    tool_name: str
    action_name: str
    index: int
    total: int
    message: str | None


def render_fetch_all_tools(
    runtime: LintRuntimeContext,
    *,
    phase_order: tuple[str, ...],
) -> int:
    """Fetch tool runtimes, emit a summary table, and return the exit status.

    Args:
        runtime: Prepared lint runtime context containing configuration and
            orchestrator collaborators.
        phase_order: Preferred ordering of tool phases for summary rendering.

    Returns:
        int: Zero when the fetch completes without orchestration failures.
    """

    config = runtime.config
    state = runtime.state
    total_actions = sum(len(tool.actions) for tool in DEFAULT_REGISTRY.tools())
    progress_enabled = total_actions > 0 and not state.display.quiet and not config.output.quiet and detect_tty()
    console = get_console_manager().get(color=config.output.color, emoji=config.output.emoji)
    verbose = state.display.verbose

    results = (
        _fetch_with_progress(runtime, total_actions, console, verbose)
        if progress_enabled
        else list(runtime.orchestrator.fetch_all_tools(config, root=runtime.state.root))
    )

    _render_fetch_summary(console, config, state, results, phase_order)
    return 0


def _fetch_with_progress(
    runtime: LintRuntimeContext,
    total_actions: int,
    console: Console,
    verbose: bool,
) -> FetchResult:
    """Return fetch results while rendering a progress bar.

    Args:
        runtime: Prepared lint runtime context containing configuration and
            orchestrator collaborators.
        total_actions: Number of tool preparation actions across the registry.
        console: Rich console used to render progress output.
        verbose: Flag indicating whether verbose logging is enabled.

    Returns:
        FetchResult: Sequence describing the preparation outcome for each
        tool action.
    """

    logger = runtime.state.logger
    progress = Progress(
        SpinnerColumn(),
        TextColumn("{task.description}"),
        BarColumn(bar_width=None),
        TimeElapsedColumn(),
        console=console,
        transient=not verbose,
    )
    task_id = progress.add_task("Preparing tools", total=total_actions)

    def progress_callback(*payload: object) -> None:
        record = _coerce_progress_record(payload)
        description = f"{record.tool_name}:{record.action_name}"
        if record.event == EVENT_START:
            status = "Preparing"
            completed = record.index - 1
        elif record.event == EVENT_COMPLETED:
            status = "Prepared"
            completed = record.index
        else:
            status = "Error"
            completed = record.index
            if record.message:
                logger.warn(f"Failed to prepare {description}: {record.message}")
                if verbose:
                    console.print(f"[red]{description} failed: {record.message}[/red]")
        progress.update(
            task_id,
            completed=completed,
            total=record.total,
            description=f"{status} {description}",
        )

    with progress:
        results = runtime.orchestrator.fetch_all_tools(
            runtime.config,
            root=runtime.state.root,
            callback=progress_callback,
        )
    return list(results)


def _render_fetch_summary(
    console: Console,
    config: Config,
    state: PreparedLintState,
    results: FetchResult,
    phase_order: tuple[str, ...],
) -> None:
    """Render a summary table describing tool preparation results.

    Args:
        console: Rich console used for table rendering.
        config: Effective configuration controlling output styling.
        state: Prepared CLI state containing display toggles and logger.
        results: Sequence describing the preparation outcome for each action.
        phase_order: Preferred ordering of tool phases for summary rendering.
    """

    if state.display.quiet:
        return

    logger = state.logger
    tool_lookup = {tool.name: tool for tool in DEFAULT_REGISTRY.tools()}
    phase_rank = {
        name: (phase_order.index(tool.phase) if tool.phase in phase_order else len(phase_order))
        for name, tool in tool_lookup.items()
    }
    sorted_results = sorted(
        results,
        key=lambda item: (
            phase_rank.get(item[0], len(phase_order)),
            item[0],
            item[1],
        ),
    )

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
    failures: list[str] = []
    for item in sorted_results:
        row, failure = _format_fetch_row(
            item,
            tool_lookup=tool_lookup,
            color_enabled=config.output.color,
        )
        table.add_row(*row)
        if failure:
            failures.append(failure)
    console.print(table)
    logger.ok(f"Prepared {len(results)} tool action(s) without execution.")
    for failure in failures:
        logger.warn(failure)


def _coerce_progress_record(payload: tuple[object, ...]) -> _FetchProgressRecord:
    """Convert an arbitrary payload into a typed progress record.

    Args:
        payload: Tuple emitted by the orchestrator progress callback.

    Returns:
        _FetchProgressRecord: Structured progress event ready for rendering.

    Raises:
        ValueError: If the payload size or event type is unsupported.
        TypeError: If payload elements do not match the expected types.
    """

    if len(payload) != PROGRESS_PAYLOAD_SIZE:
        raise ValueError("unexpected progress payload")
    event, tool_name, action_name, index, total, message = payload
    if not isinstance(event, str):
        raise TypeError("event must be a string")
    if event not in {EVENT_START, EVENT_COMPLETED, EVENT_ERROR}:
        raise ValueError(f"unsupported progress event: {event}")
    if not isinstance(tool_name, str) or not isinstance(action_name, str):
        raise TypeError("tool name and action name must be strings")
    if not isinstance(index, int) or not isinstance(total, int):
        raise TypeError("index and total must be integers")
    if message is not None and not isinstance(message, str):
        raise TypeError("message must be a string when provided")
    return _FetchProgressRecord(
        event=cast(ProgressEventLiteral, event),
        tool_name=tool_name,
        action_name=action_name,
        index=index,
        total=total,
        message=message,
    )


def _format_fetch_row(
    item: tuple[str, str, PreparedCommand | None, str | None],
    *,
    tool_lookup: Mapping[str, Tool],
    color_enabled: bool,
) -> tuple[tuple[str, str, str, str, str, str], str | None]:
    """Return a formatted summary row and optional failure message.

    Args:
        item: Tuple containing tool name, action, prepared command, and error.
        tool_lookup: Mapping of tool names to registry tool instances.
        color_enabled: Flag indicating whether colorized output is permitted.

    Returns:
        tuple[tuple[str, str, str, str, str, str], str | None]: Formatted row
        columns plus a failure message when the preparation failed.
    """

    tool_name, action_name, prepared, error = item
    phase = getattr(tool_lookup.get(tool_name), "phase", "-")
    if prepared is None:
        status = "error"
        source = "-"
        version = "-"
        failure_message = f"Failed to prepare {tool_name}:{action_name} — {error or 'unknown error'}"
    else:
        status = "ready"
        source = prepared.source
        version = prepared.version or "unknown"
        failure_message = None
    if color_enabled:
        status = "[red]error[/]" if failure_message else "[green]ready[/]"
    row = (tool_name, action_name, phase, status, source, version)
    return row, failure_message
