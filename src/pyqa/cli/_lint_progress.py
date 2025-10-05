# SPDX-License-Identifier: MIT
"""Progress rendering helpers for lint execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from typing import TYPE_CHECKING, Final, Literal

from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
)
from rich.text import Text

from ..console import console_manager
from ._lint_literals import OUTPUT_MODE_CONCISE

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

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from rich.console import Console

    from ..execution.orchestrator import OrchestratorHooks
    from ..models import RunResult, ToolOutcome
    from ._lint_runtime import LintRuntimeContext


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
        config = self.runtime.config
        state = self.runtime.state
        self.enabled = (
            config.output.output == OUTPUT_MODE_CONCISE
            and not state.display.quiet
            and not config.output.quiet
            and config.output.color
            and self.is_terminal
        )
        if not self.enabled:
            return

        console = console_manager.get(color=config.output.color, emoji=config.output.emoji)
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
        width = getattr(console.size, "width", 100)
        reserved = 40
        available = max(10, width - reserved)
        return max(20, int(available * 0.8))

    def install(self, hooks: OrchestratorHooks) -> None:
        """Attach progress callbacks to ``hooks`` when progress is enabled."""

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
            color_enabled = self.runtime.config.output.color
            status_value = "[cyan]rendering output[/]" if color_enabled else STATUS_RENDERING
            progress.update(task_id, current_status=status_value)

    def finalize(self, success: bool) -> Text | None:
        """Finalize the progress display and return a summary message."""

        if not self.enabled or self.context is None:
            return None
        progress = self.context.progress
        task_id = self.context.task_id
        lock = self.context.lock
        with lock:
            status_literal = STATUS_DONE if success else STATUS_ISSUES
            color_enabled = self.runtime.config.output.color
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
        progress_context = self.context
        if progress_context is None:
            return
        progress_context.progress.advance(progress_context.task_id, advance=amount)
        self.state.completed += amount

    @property
    def console(self) -> Console | None:
        """Return the Rich console used for rendering when progress is enabled."""

        return None if self.context is None else self.context.console

    def advance(self, amount: int) -> None:
        """Public helper used by callbacks to advance the progress bar."""

        self._advance(amount)


@dataclass(slots=True)
class _ProgressCallbacks:
    """Encapsulate Rich progress callbacks for lint execution."""

    controller: ExecutionProgressController
    progress: Progress
    task_id: TaskID
    lock: Lock

    def register(self, hooks: OrchestratorHooks) -> None:
        """Bind callbacks onto the orchestrator hooks."""

        hooks.before_tool = self.before_tool
        hooks.after_tool = self.after_tool
        hooks.after_discovery = self.after_discovery
        hooks.after_execution = self.after_execution
        hooks.after_plan = self.after_plan

    def before_tool(self, tool_name: str) -> None:
        """Update progress prior to running ``tool_name``."""

        with self.lock:
            self._ensure_started()
            self.progress.update(
                self.task_id,
                description=f"Linting {tool_name}",
                current_status=self._status_markup(STATUS_RUNNING, color="yellow"),
            )

    def after_tool(self, outcome: ToolOutcome) -> None:
        """Advance progress after the orchestrator finishes a tool."""

        with self.lock:
            self._ensure_started()
            self.controller.advance(1)
            status_markup = self._tool_status(outcome)
            self.progress.update(
                self.task_id,
                current_status=f"{outcome.tool}:{outcome.action} {status_markup}",
            )

    def after_discovery(self, file_count: int) -> None:
        """Render progress information after file discovery completes."""

        with self.lock:
            self._ensure_started()
            status = self._status_markup(STATUS_QUEUED, color="cyan")
            self.progress.update(
                self.task_id,
                description=f"Linting ({file_count} files)",
                current_status=status,
            )

    def after_execution(self, _result: RunResult) -> None:
        """Advance the bar after orchestrator execution completes."""

        with self.lock:
            self._ensure_started()
            self.controller.advance(1)
            status = self._status_markup(STATUS_POST_PROCESSING, color="cyan")
            self.progress.update(self.task_id, current_status=status)

    def after_plan(self, total_actions: int) -> None:
        """Update the total number of actions once the plan is known."""

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
        """Return colour-aware status markup for ``outcome``."""

        if outcome.cached:
            return self._status_markup("cached", color="cyan")
        if outcome.ok:
            return self._status_markup("ok", color="green")
        return self._status_markup("issues", color="red")

    def _status_markup(self, label: str, *, color: str) -> str:
        """Return ``label`` optionally wrapped with colour markup."""

        if not self.controller.runtime.config.output.color:
            return label
        return f"[{color}]{label}[/]"


__all__ = ["ExecutionProgressController"]
