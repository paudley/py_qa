# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Helpers for rendering fetch-all-tools output in the CLI."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Final, Literal, TypeAlias

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
from pyqa.interfaces.config import Config as ConfigProtocol
from pyqa.interfaces.linting import PreparedLintState as PreparedLintStateView
from pyqa.runtime.console.manager import detect_tty, get_console_manager

from ....tools.base import Tool
from ....tools.registry import DEFAULT_REGISTRY
from .runtime import LintRuntimeContext

FetchResult = list[tuple[str, str, PreparedCommand | None, str | None]]
ProgressEventLiteral = Literal["start", "completed", "error"]
EVENT_START: Final[ProgressEventLiteral] = "start"
EVENT_COMPLETED: Final[ProgressEventLiteral] = "completed"
EVENT_ERROR: Final[ProgressEventLiteral] = "error"
PROGRESS_PAYLOAD_SIZE: Final[int] = 6

ProgressPayload: TypeAlias = tuple[
    ProgressEventLiteral,
    str,
    str,
    int,
    int,
    str | None,
]

_EVENT_LOOKUP: dict[str, ProgressEventLiteral] = {
    EVENT_START: EVENT_START,
    EVENT_COMPLETED: EVENT_COMPLETED,
    EVENT_ERROR: EVENT_ERROR,
}


@dataclass(frozen=True)
class ProgressEventData:
    """Structured progress event metadata emitted by the orchestrator."""

    event: str
    tool_name: str
    action_name: str
    index: int
    total: int
    message: str | None


@dataclass(frozen=True)
class _ProgressHandler:
    """Adapter that converts orchestrator events into payload tuples."""

    handler: Callable[[ProgressPayload], None]

    def process(self, data: ProgressEventData) -> None:
        """Convert ``data`` into a :class:`ProgressPayload` and dispatch it.

        Args:
            data: Structured progress event emitted by the orchestrator.
        """

        payload = _progress_payload_from_data(data)
        self.handler(payload)


def _wrap_progress_handler(
    handler: Callable[[ProgressPayload], None],
) -> Callable[[str, str, str, int, int, str | None], None]:
    """Return a callback adapting orchestrator progress events into payload tuples.

    Args:
        handler: Callable receiving structured progress payloads.

    Returns:
        Callable[[str, str, str, int, int, str | None], None]: Adapter matching the
        orchestrator's progress callback signature.
    """

    adapter = _ProgressHandler(handler)
    return lambda event, tool_name, action_name, index, total, message: adapter.process(
        ProgressEventData(
            event=event,
            tool_name=tool_name,
            action_name=action_name,
            index=index,
            total=total,
            message=message,
        ),
    )


def _progress_payload_from_data(data: ProgressEventData) -> ProgressPayload:
    """Return a structured payload tuple derived from ``data``.

    Args:
        data: Progress event containing metadata for the current tool action.

    Returns:
        ProgressPayload: Tuple suitable for downstream rendering and logging.
    """

    return (
        _coerce_progress_event(data.event),
        data.tool_name,
        data.action_name,
        data.index,
        data.total,
        data.message,
    )


def _coerce_progress_event(event: str) -> ProgressEventLiteral:
    """Return ``event`` coerced into a known progress event literal.

    Args:
        event: Raw event string provided by the orchestrator.

    Returns:
        ProgressEventLiteral: Normalised event literal understood by the CLI.

    Raises:
        ValueError: If ``event`` is not recognised.
    """

    literal = _EVENT_LOOKUP.get(event)
    if literal is None:
        raise ValueError(f"Unknown progress event: {event}")
    return literal


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

    state = runtime.state
    logger = state.logger
    progress = Progress(
        SpinnerColumn(),
        TextColumn("{task.description}"),
        BarColumn(bar_width=None),
        TimeElapsedColumn(),
        console=console,
        transient=not verbose,
    )
    task_id = progress.add_task("Preparing tools", total=total_actions)

    def handle_progress(payload: ProgressPayload) -> None:
        """Update progress state based on ``payload`` emitted by orchestrator.

        Args:
            payload: Tuple describing the current tool preparation event.
        """

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

    progress_callback = _wrap_progress_handler(handle_progress)

    with progress:
        results = runtime.orchestrator.fetch_all_tools(
            runtime.config,
            root=state.root,
            callback=progress_callback,
        )
    return list(results)


def _render_fetch_summary(
    console: Console,
    config: ConfigProtocol,
    state: PreparedLintStateView,
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


def _coerce_progress_record(payload: ProgressPayload) -> _FetchProgressRecord:
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
    if event not in {EVENT_START, EVENT_COMPLETED, EVENT_ERROR}:
        raise ValueError(f"unsupported progress event: {event}")
    if not isinstance(tool_name, str) or not isinstance(action_name, str):
        raise TypeError("tool name and action name must be strings")
    if not isinstance(index, int) or not isinstance(total, int):
        raise TypeError("index and total must be integers")
    if message is not None and not isinstance(message, str):
        raise TypeError("message must be a string when provided")
    return _FetchProgressRecord(
        event=event,
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
