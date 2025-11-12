# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Progress rendering helpers for lint execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from typing import Final, Literal

from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskID, TextColumn, TimeElapsedColumn
from rich.text import Text

from pyqa.runtime.console.manager import get_console_manager

from ....cli.core.lint_literals import OUTPUT_MODE_CONCISE
from ....core.models import RunResult, ToolOutcome
from ....core.runtime import ServiceResolutionError
from ....interfaces.orchestration import OrchestratorHooks
from .runtime import LintRuntimeContext

ProgressStatusLiteral = Literal[
    "waiting",
    "running",
    "queued",
    "post-processing",
    "rendering output",
    "done",
    "issues detected",
]

STATUS_WAITING: Final[ProgressStatusLiteral] = "waiting"
STATUS_RUNNING: Final[ProgressStatusLiteral] = "running"
STATUS_QUEUED: Final[ProgressStatusLiteral] = "queued"
STATUS_POST_PROCESSING: Final[ProgressStatusLiteral] = "post-processing"
STATUS_RENDERING: Final[ProgressStatusLiteral] = "rendering output"
STATUS_DONE: Final[ProgressStatusLiteral] = "done"
STATUS_ISSUES: Final[ProgressStatusLiteral] = "issues detected"


@dataclass(slots=True)
class ProgressContext:
    """Runtime context required to render lint progress."""

    progress: Progress
    task_id: TaskID
    console: Console
    lock: Lock


@dataclass(slots=True)
class ProgressState:
    """Mutable counters tracking progress lifecycle state."""

    total: int = 0
    completed: int = 0
    started: bool = False


@dataclass(slots=True)
class ExecutionProgressController:
    """Manage orchestrator progress feedback for lint execution."""

    runtime: LintRuntimeContext
    is_terminal: bool = True
    extra_phases: int = 2
    progress_factory: type[Progress] = Progress
    enabled: bool = field(init=False, default=False)
    context: ProgressContext | None = field(init=False, default=None)
    state: ProgressState = field(init=False, default_factory=ProgressState)

    def __post_init__(self) -> None:
        """Initialise the controller and optionally create a progress bar."""

        config = self.runtime.config
        state = self.runtime.state
        output_mode = getattr(config.output, "output", OUTPUT_MODE_CONCISE)
        color_allowed = self.is_terminal and config.output.color
        self.enabled = (
            color_allowed and not state.display.quiet and not config.output.quiet and output_mode == OUTPUT_MODE_CONCISE
        )
        if not self.enabled:
            return

        console_factory = get_console_manager().get
        services = getattr(self.runtime, "services", None)
        if services is not None:
            try:
                console_factory = services.resolve("console_factory")
            except ServiceResolutionError:
                console_factory = get_console_manager().get
        color_enabled = color_allowed
        console = console_factory(color=color_enabled, emoji=config.output.emoji)
        progress = self.progress_factory(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(bar_width=self._determine_bar_width(console)),
            TextColumn("{task.completed}/{task.total}"),
            TimeElapsedColumn(),
            TextColumn("{task.fields[current_status]}", justify="right"),
            console=console,
            transient=True,
        )
        task_id = progress.add_task(
            "Linting",
            total=self.extra_phases,
            current_status=STATUS_WAITING,
        )
        lock = Lock()
        self.context = ProgressContext(progress=progress, task_id=task_id, console=console, lock=lock)
        self.state.total = self.extra_phases

    @staticmethod
    def _determine_bar_width(console: Console) -> int:
        """Return an appropriate bar width for the provided console.

        Args:
            console: Rich console used to render the progress bar.

        Returns:
            int: Width in characters for the progress bar component.
        """

        width = getattr(console.size, "width", 100)
        reserved = 40
        available = max(10, width - reserved)
        return max(20, int(available * 0.8))

    def install(self, hooks: OrchestratorHooks) -> None:
        """Attach progress callbacks to orchestrator hooks when enabled.

        Args:
            hooks: Orchestrator hook container receiving lifecycle callbacks.
        """

        if not self.enabled or self.context is None:
            return
        callbacks = _ProgressCallbacks(
            controller=self,
            progress=self.context.progress,
            task_id=self.context.task_id,
            lock=self.context.lock,
        )
        callbacks.register(hooks)

    def advance_rendering_phase(self) -> None:
        """Advance the progress bar once output rendering begins."""

        if not self.enabled or self.context is None:
            return
        progress = self.context.progress
        task_id = self.context.task_id
        lock = self.context.lock
        with lock:
            self._advance(1)
        color_enabled = self.runtime.config.output.color and self.is_terminal
        status_value = "[cyan]rendering output[/]" if color_enabled else STATUS_RENDERING
        progress.update(task_id, current_status=status_value)

    def finalize(self, success: bool) -> Text | None:
        """Finalize the progress display and return a summary message.

        Args:
            success: Indicator that determines the final status styling.

        Returns:
            Text | None: Summary text when progress was rendered, otherwise
            ``None`` when progress was disabled.
        """

        if not self.enabled or self.context is None:
            return None
        progress = self.context.progress
        task_id = self.context.task_id
        lock = self.context.lock
        color_enabled = self.runtime.config.output.color and self.is_terminal
        with lock:
            status_literal = STATUS_DONE if success else STATUS_ISSUES
            status_value = (
                ("[green]done[/]" if success else "[red]issues detected[/]") if color_enabled else status_literal
            )
            total = max(self.state.total, self.state.completed)
            progress.update(task_id, total=total, current_status=status_value)
        if color_enabled:
            return Text.from_markup(status_value)
        return Text(status_literal)

    def stop(self) -> None:
        """Stop the progress bar if it was previously started."""

        if not self.enabled or self.context is None:
            return
        if self.state.started:
            self.context.progress.stop()

    def _advance(self, amount: int) -> None:
        """Advance internal counters and the progress bar by ``amount``.

        Args:
            amount: Number of steps to advance the progress bar.
        """

        progress_context = self.context
        if progress_context is None:
            return
        progress_context.progress.advance(progress_context.task_id, advance=amount)
        self.state.completed += amount

    @property
    def console(self) -> Console | None:
        """Return the Rich console used for rendering when progress is enabled.

        Returns:
            Console | None: Console instance when progress was initialised,
            otherwise ``None``.
        """

        return None if self.context is None else self.context.console

    def advance(self, amount: int) -> None:
        """Advance the progress bar by ``amount`` on behalf of callbacks.

        Args:
            amount: Number of steps to advance the progress bar.
        """

        self._advance(amount)


@dataclass(slots=True)
class _ProgressCallbacks:
    """Encapsulate Rich progress callbacks for lint execution."""

    controller: ExecutionProgressController
    progress: Progress
    task_id: TaskID
    lock: Lock

    def register(self, hooks: OrchestratorHooks) -> None:
        """Bind callbacks onto the orchestrator hooks.

        Args:
            hooks: Orchestrator hook container receiving lifecycle callbacks.
        """

        hooks.before_tool = self.before_tool
        hooks.after_tool = self.after_tool
        hooks.after_discovery = self.after_discovery
        hooks.after_execution = self.after_execution
        hooks.after_plan = self.after_plan

    def before_tool(self, tool_name: str) -> None:
        """Update progress prior to running ``tool_name``.

        Args:
            tool_name: Name of the tool about to execute.
        """

        with self.lock:
            self._ensure_started()
            self.progress.update(
                self.task_id,
                description=f"Linting {tool_name}",
                current_status=self._status_markup(STATUS_RUNNING, color="yellow"),
            )

    def after_tool(self, outcome: ToolOutcome) -> None:
        """Advance progress after the orchestrator finishes a tool.

        Args:
            outcome: Tool outcome produced by the orchestrator.
        """

        with self.lock:
            self._ensure_started()
            self.controller.advance(1)
            status_markup = self._tool_status(outcome)
            self.progress.update(
                self.task_id,
                current_status=f"{outcome.tool}:{outcome.action} {status_markup}",
            )

    def after_discovery(self, file_count: int) -> None:
        """Render progress information after file discovery completes.

        Args:
            file_count: Number of files identified during discovery.
        """

        with self.lock:
            self._ensure_started()
            status = self._status_markup(STATUS_QUEUED, color="cyan")
            self.progress.update(
                self.task_id,
                description=f"Linting ({file_count} files)",
                current_status=status,
            )

    def after_execution(self, result: RunResult) -> None:
        """Advance the bar after orchestrator execution completes.

        Args:
            result: Run result produced by the orchestrator, used to surface the number
                of diagnostics processed during post-run reporting.
        """

        diagnostic_total = result.diagnostic_count()
        with self.lock:
            self._ensure_started()
            self.controller.advance(1)
            status = self._status_markup(STATUS_POST_PROCESSING, color="cyan")
            if diagnostic_total:
                status = f"{status} ({diagnostic_total} diagnostics)"
            self.progress.update(self.task_id, current_status=status)

    def after_plan(self, total_actions: int) -> None:
        """Update the total number of actions once the plan is known.

        Args:
            total_actions: Total number of planned tool actions.
        """

        with self.lock:
            self._ensure_started()
            self.controller.state.total = total_actions + self.controller.extra_phases
            self.progress.update(self.task_id, total=self.controller.state.total)

    # Helper utilities -----------------------------------------------------------------

    def _ensure_started(self) -> None:
        """Start the Rich progress bar when the first update arrives."""

        if not self.controller.state.started:
            self.progress.start()
            self.controller.state.started = True

    def _tool_status(self, outcome: ToolOutcome) -> str:
        """Return colour-aware status markup for ``outcome``.

        Args:
            outcome: Tool outcome emitted by the orchestrator.

        Returns:
            str: Status string optionally wrapped with colour markup.
        """

        if outcome.cached:
            return self._status_markup("cached", color="cyan")
        if outcome.ok:
            return self._status_markup("ok", color="green")
        return self._status_markup("issues", color="red")

    def _status_markup(self, label: str, *, color: str) -> str:
        """Return ``label`` optionally wrapped with colour markup.

        Args:
            label: Status label to render.
            color: Colour name applied when colour output is enabled.

        Returns:
            str: Markup string suitable for Rich rendering.
        """

        if not self.controller.runtime.config.output.color:
            return label
        return f"[{color}]{label}[/]"


__all__ = ["ExecutionProgressController"]
