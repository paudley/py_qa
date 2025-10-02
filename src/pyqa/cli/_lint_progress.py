# SPDX-License-Identifier: MIT
"""Progress rendering helpers for lint execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from typing import TYPE_CHECKING

from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.text import Text

from ..console import console_manager

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from rich.console import Console
    from ..execution.orchestrator import OrchestratorHooks
    from ..reporting.formatters import OutputConfig
    from .lint import LintRuntimeContext


@dataclass(slots=True)
class ExecutionProgressController:
    """Manage orchestrator progress feedback for lint execution."""

    runtime: "LintRuntimeContext"
    is_terminal: bool = True
    extra_phases: int = 2
    progress_factory: type[Progress] = Progress
    enabled: bool = field(init=False, default=False)
    progress: Progress | None = field(init=False, default=None)
    task_id: int | None = field(init=False, default=None)
    console: "Console | None" = field(init=False, default=None)
    lock: Lock | None = field(init=False, default=None)
    total: int = field(init=False, default=0)
    completed: int = field(init=False, default=0)
    started: bool = field(init=False, default=False)

    def __post_init__(self) -> None:
        config = self.runtime.config
        state = self.runtime.state
        self.enabled = (
            config.output.output == "concise"
            and not state.display.quiet
            and not config.output.quiet
            and config.output.color
            and self.is_terminal
        )
        if not self.enabled:
            return

        self.console = console_manager.get(color=config.output.color, emoji=config.output.emoji)
        self.progress = self.progress_factory(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(bar_width=self._determine_bar_width(self.console)),
            TextColumn("{task.completed}/{task.total}"),
            TimeElapsedColumn(),
            TextColumn("{task.fields[current_status]}", justify="right"),
            console=self.console,
            transient=True,
        )
        self.task_id = self.progress.add_task(
            "Linting",
            total=self.extra_phases,
            current_status="waiting",
        )
        self.lock = Lock()
        self.total = self.extra_phases

    @staticmethod
    def _determine_bar_width(console: "Console") -> int:
        width = getattr(console.size, "width", 100)
        reserved = 40
        available = max(10, width - reserved)
        return max(20, int(available * 0.8))

    def install(self, hooks: "OrchestratorHooks") -> None:
        if not self.enabled or not self.progress or self.task_id is None:
            return

        def ensure_started() -> None:
            if not self.started:
                self.progress.start()
                self.started = True

        def before_tool(tool_name: str) -> None:
            with self.lock:
                ensure_started()
                self.progress.update(
                    self.task_id,
                    description=f"Linting {tool_name}",
                    current_status="running",
                )

        def after_tool(outcome) -> None:  # noqa: ANN001
            with self.lock:
                ensure_started()
                self._advance(1)
                status = "ok" if outcome.ok else "issues"
                if self.runtime.config.output.color:
                    status = "[green]ok[/]" if outcome.ok else "[red]issues[/]"
                self.progress.update(
                    self.task_id,
                    current_status=f"{outcome.tool}:{outcome.action} {status}",
                )

        def after_discovery(file_count: int) -> None:
            with self.lock:
                ensure_started()
                status = "queued"
                if self.runtime.config.output.color:
                    status = "[cyan]queued[/]"
                self.progress.update(
                    self.task_id,
                    description=f"Linting ({file_count} files)",
                    current_status=status,
                )

        def after_execution_hook(_result) -> None:  # noqa: ANN001
            with self.lock:
                ensure_started()
                self._advance(1)
                status = "post-processing"
                if self.runtime.config.output.color:
                    status = "[cyan]post-processing[/]"
                self.progress.update(
                    self.task_id,
                    current_status=status,
                )

        def after_plan_hook(total_actions: int) -> None:
            with self.lock:
                ensure_started()
                self.total = total_actions + self.extra_phases
                self.progress.update(self.task_id, total=self.total)

        hooks.before_tool = before_tool
        hooks.after_tool = after_tool
        hooks.after_discovery = after_discovery
        hooks.after_execution = after_execution_hook
        hooks.after_plan = after_plan_hook

    def advance_rendering_phase(self) -> None:
        if not self.enabled or not self.progress or self.task_id is None:
            return
        with self.lock:
            self._advance(1)
            status = "rendering output"
            if self.runtime.config.output.color:
                status = "[cyan]rendering output[/]"
            self.progress.update(self.task_id, current_status=status)

    def finalize(self, success: bool) -> Text | None:
        if not self.enabled or not self.progress or self.task_id is None:
            return None
        with self.lock:
            status_text = "done" if success else "issues detected"
            if self.runtime.config.output.color:
                status_text = "[green]done[/]" if success else "[red]issues detected[/]"
            total = max(self.total, self.completed)
            self.progress.update(self.task_id, total=total, current_status=status_text)
        return Text.from_markup(status_text) if self.runtime.config.output.color else Text(status_text)

    def stop(self) -> None:
        if not self.enabled or not self.progress:
            return
        if self.started:
            self.progress.stop()

    def _advance(self, amount: int) -> None:
        if not self.progress or self.task_id is None:
            return
        self.progress.advance(self.task_id, advance=amount)
        self.completed += amount


__all__ = ["ExecutionProgressController"]
