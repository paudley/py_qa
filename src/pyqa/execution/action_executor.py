# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Execution helpers for running tool actions and recording outcomes."""

from __future__ import annotations

import shlex
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from subprocess import CompletedProcess
from textwrap import shorten
from typing import Final, Protocol, runtime_checkable

from ..cache.context import CacheContext
from ..cache.result_store import CacheRequest
from ..config import Config
from ..context import CONTEXT_RESOLVER
from ..diagnostics import normalize_diagnostics
from ..execution.diagnostic_filter import filter_diagnostics
from ..filesystem.paths import normalize_path_key
from ..logging import warn
from ..metrics import FileMetrics, compute_file_metrics
from ..models import Diagnostic, RawDiagnostic, ToolOutcome
from ..process_utils import CommandOptions
from ..severity import SeverityRuleView
from ..tools import ToolAction, ToolContext


@runtime_checkable
class RunnerCallable(Protocol):
    """Callable protocol for invoking external tool commands."""

    def __call__(
        self,
        cmd: Sequence[str],
        *,
        options: CommandOptions | None = None,
        **overrides: object,
    ) -> CompletedProcess[str]:
        """Execute ``cmd`` returning a completed subprocess.

        Args:
            cmd: Command to execute including executable and arguments.
            options: Optional command execution configuration overrides.
            **overrides: Additional keyword arguments forwarded to the runner.

        Returns:
            CompletedProcess[str]: Completed subprocess with captured output.

        Raises:
            NotImplementedError: Always raised; method must be provided by
                concrete runner implementations.
        """

        raise NotImplementedError

    def __repr__(self) -> str:
        """Return a diagnostic representation of the runner.

        Returns:
            str: Readable description for debugging.

        Raises:
            NotImplementedError: Always raised; method must be provided by
                concrete implementations.
        """

        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class FunctionRunner:
    """Adapter that turns plain callables into :class:`RunnerCallable` objects."""

    func: Callable[..., CompletedProcess[str]]

    def __call__(
        self,
        cmd: Sequence[str],
        *,
        options: CommandOptions | None = None,
        **overrides: object,
    ) -> CompletedProcess[str]:
        """Invoke the wrapped callable using runner semantics.

        Args:
            cmd: Command to execute.
            options: Optional execution options overriding defaults.
            **overrides: Additional keyword arguments forwarded to the wrapped callable.

        Returns:
            CompletedProcess[str]: Completed process metadata.
        """

        return self.func(cmd, options=options, **overrides)

    def __repr__(self) -> str:
        """Return a descriptive representation of the wrapped callable.

        Returns:
            str: Readable description based on the wrapped callable.
        """

        qualname = getattr(self.func, "__qualname__", None)
        module = getattr(self.func, "__module__", None)
        if qualname and module:
            return f"FunctionRunner({module}.{qualname})"
        return f"FunctionRunner({self.func!r})"


def wrap_runner(func: Callable[..., CompletedProcess[str]]) -> RunnerCallable:
    """Return a :class:`RunnerCallable` that delegates to ``func``.

    Args:
        func: Callable implementing the runner protocol.

    Returns:
        RunnerCallable: Adapter object implementing the runner protocol.
    """

    if isinstance(func, RunnerCallable):
        return func
    return FunctionRunner(func)


PYLINT_TOOL_NAME: Final[str] = "pylint"
TOMBI_TOOL_NAME: Final[str] = "tombi"
_IGNORED_CHECK_RETURN_CODES: Final[frozenset[int]] = frozenset({1})


@dataclass(frozen=True, slots=True)
class ExecutionEnvironment:
    """Immutable description of the execution environment for actions."""

    config: Config
    root: Path
    severity_rules: SeverityRuleView
    cache: CacheContext


@dataclass(frozen=True, slots=True)
class ActionInvocation:
    """Concrete plan for invoking a tool action."""

    tool_name: str
    action: ToolAction
    context: ToolContext
    command: tuple[str, ...]
    env_overrides: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class ScheduledAction:
    """Immutable execution entry queued for deferred execution."""

    order: int
    invocation: ActionInvocation


@dataclass(frozen=True, slots=True)
class OutcomeRecord:
    """Rich outcome metadata destined for state persistence."""

    order: int
    invocation: ActionInvocation
    outcome: ToolOutcome
    file_metrics: Mapping[str, FileMetrics] | None
    from_cache: bool


@dataclass(slots=True)
class ExecutionState:
    """Mutable state accumulated across orchestrated tool runs."""

    outcomes: dict[int, ToolOutcome] = field(default_factory=dict)
    scheduled: list[ScheduledAction] = field(default_factory=list)
    order: int = 0
    bail_triggered: bool = False
    file_metrics: dict[str, FileMetrics] = field(default_factory=dict)
    installed_tools: set[str] = field(default_factory=set)


@dataclass(slots=True)
class ActionExecutor:
    """Execute tool actions and synchronise resulting state."""

    runner: RunnerCallable
    after_tool_hook: Callable[[ToolOutcome], None] | None

    def execute_scheduled(self, environment: ExecutionEnvironment, state: ExecutionState) -> None:
        """Run all queued actions honouring concurrency constraints.

        Args:
            environment: Execution environment configuration shared by the run.
            state: Mutable execution state that stores outcomes and metrics.
        """

        if not state.scheduled:
            return
        if environment.config.execution.bail and state.bail_triggered:
            state.scheduled.clear()
            return
        if environment.config.execution.jobs > 1:
            self._execute_in_parallel(environment, state)
        else:
            self._execute_serial(environment, state)

    def populate_missing_metrics(self, state: ExecutionState, files: Sequence[Path]) -> None:
        """Ensure every discovered file has an associated metrics entry.

        Args:
            state: Execution state storing metrics collected so far.
            files: Files discovered for the current run.
        """

        for path in files:
            key = normalize_path_key(path)
            if key in state.file_metrics:
                continue
            state.file_metrics[key] = compute_file_metrics(path)

    def collect_metrics_for_files(self, state: ExecutionState, files: Sequence[Path]) -> dict[str, FileMetrics]:
        """Return metrics for ``files`` pulling from cache or recomputing.

        Args:
            state: Execution state tracking previously gathered metrics.
            files: Files whose metrics should be retrieved or recomputed.

        Returns:
            dict[str, FileMetrics]: Mapping from normalized path key to metrics.
        """

        collected: dict[str, FileMetrics] = {}
        for path in files:
            key = normalize_path_key(path)
            metric = state.file_metrics.get(key)
            if metric is None:
                metric = compute_file_metrics(path)
            metric.ensure_labels()
            collected[key] = metric
        return collected

    def record_outcome(
        self,
        state: ExecutionState,
        environment: ExecutionEnvironment,
        record: OutcomeRecord,
    ) -> None:
        """Persist an outcome locally and optionally store it in the cache.

        Args:
            state: Mutable execution state shared across the orchestrator.
            environment: Execution environment containing cache configuration.
            record: Outcome metadata slated for persistence.
        """

        invocation = record.invocation
        metrics_map = (
            dict(record.file_metrics)
            if record.file_metrics is not None
            else self.collect_metrics_for_files(state, invocation.context.files)
        )
        self._update_state_metrics(state, metrics_map)
        outcome = record.outcome
        outcome.cached = record.from_cache
        if record.from_cache:
            filters = invocation.context.cfg.output.tool_filters.get(invocation.tool_name, [])
            outcome.diagnostics = filter_diagnostics(
                outcome.diagnostics,
                invocation.tool_name,
                filters,
                environment.root,
            )
            adjusted = self._adjust_returncode(
                invocation.tool_name,
                outcome.returncode,
                outcome.diagnostics,
                ignore_exit=invocation.action.ignore_exit,
            )
            outcome.returncode = adjusted
        state.outcomes[record.order] = outcome
        if (
            record.from_cache
            and outcome.returncode != 0
            and not record.invocation.action.ignore_exit
            and not outcome.diagnostics
        ):
            cached_process = CompletedProcess(
                list(record.invocation.command),
                returncode=outcome.returncode,
                stdout="\n".join(outcome.stdout),
                stderr="\n".join(outcome.stderr),
            )
            _log_action_failure(
                invocation=record.invocation,
                completed=cached_process,
                diagnostics=tuple(outcome.diagnostics),
                root=environment.root,
                from_cache=True,
            )
        cache_ctx = environment.cache
        if cache_ctx.cache and cache_ctx.token is not None and not record.from_cache:
            request = CacheRequest(
                tool=invocation.tool_name,
                action=invocation.action.name,
                command=invocation.command,
                files=tuple(Path(path) for path in invocation.context.files),
                token=cache_ctx.token,
            )
            cache_ctx.cache.store(request, outcome=outcome, file_metrics=metrics_map)
        if self.after_tool_hook:
            self.after_tool_hook(outcome)

    def run_action(self, invocation: ActionInvocation, environment: ExecutionEnvironment) -> ToolOutcome:
        """Execute ``invocation`` and return the normalized outcome.

        Args:
            invocation: Planned tool invocation with context and command data.
            environment: Execution environment that supplies root and severity.

        Returns:
            ToolOutcome: Normalized tool output with diagnostics populated.
        """

        env = self._compose_environment(invocation)
        completed = self.runner(
            list(invocation.command),
            options=CommandOptions(
                cwd=environment.root,
                env=env,
                timeout=invocation.action.timeout_s,
                capture_output=True,
                discard_stdin=True,
                check=False,
            ),
        )
        filters = invocation.context.cfg.output.tool_filters.get(invocation.tool_name, [])
        stdout_lines, stderr_lines = self._filter_outputs(invocation, completed, filters)
        parsed = self._parse_diagnostics(invocation, stdout_lines, stderr_lines)
        diagnostics = normalize_diagnostics(
            parsed,
            tool_name=invocation.tool_name,
            severity_rules=environment.severity_rules,
        )
        diagnostics = filter_diagnostics(diagnostics, invocation.tool_name, filters, environment.root)
        adjusted_returncode = self._adjust_returncode(
            invocation.tool_name,
            completed.returncode,
            diagnostics,
            ignore_exit=invocation.action.ignore_exit,
        )

        if diagnostics:
            CONTEXT_RESOLVER.annotate(diagnostics, root=environment.root)
        should_log_failure = adjusted_returncode != 0 and not invocation.action.ignore_exit and not diagnostics
        if should_log_failure:
            _log_action_failure(
                invocation=invocation,
                completed=completed,
                diagnostics=diagnostics,
                root=environment.root,
                from_cache=False,
            )
        return ToolOutcome(
            tool=invocation.tool_name,
            action=invocation.action.name,
            returncode=adjusted_returncode,
            stdout=stdout_lines,
            stderr=stderr_lines,
            diagnostics=diagnostics,
        )

    def _execute_in_parallel(self, environment: ExecutionEnvironment, state: ExecutionState) -> None:
        """Execute scheduled actions concurrently when permitted.

        Args:
            environment: Execution environment describing runtime parameters.
            state: Mutable execution state accumulating outcomes.
        """
        action_runner = partial(self.run_action, environment=environment)
        with ThreadPoolExecutor(max_workers=environment.config.execution.jobs) as executor:
            future_map = {
                executor.submit(action_runner, scheduled.invocation): scheduled for scheduled in state.scheduled
            }
            for future in as_completed(future_map):
                scheduled = future_map[future]
                outcome = future.result()
                record = OutcomeRecord(
                    order=scheduled.order,
                    invocation=scheduled.invocation,
                    outcome=outcome,
                    file_metrics=None,
                    from_cache=False,
                )
                self.record_outcome(state, environment, record)

    def _execute_serial(self, environment: ExecutionEnvironment, state: ExecutionState) -> None:
        """Execute scheduled actions sequentially.

        Args:
            environment: Execution environment describing runtime parameters.
            state: Mutable execution state accumulating outcomes.
        """
        action_runner = partial(self.run_action, environment=environment)
        for scheduled in state.scheduled:
            outcome = action_runner(scheduled.invocation)
            record = OutcomeRecord(
                order=scheduled.order,
                invocation=scheduled.invocation,
                outcome=outcome,
                file_metrics=None,
                from_cache=False,
            )
            self.record_outcome(state, environment, record)

    @staticmethod
    def _update_state_metrics(state: ExecutionState, metrics: Mapping[str, FileMetrics]) -> None:
        """Merge ``metrics`` into ``state`` ensuring labels are present.

        Args:
            state: Execution state that stores file metrics.
            metrics: Metrics gathered for recently processed files.
        """
        for key, metric in metrics.items():
            metric.ensure_labels()
            state.file_metrics[key] = metric

    @staticmethod
    def _compose_environment(invocation: ActionInvocation) -> dict[str, str]:
        """Return the runtime environment for ``invocation``.

        Args:
            invocation: Invocation whose environment should be composed.

        Returns:
            dict[str, str]: Combined environment variables for the action.
        """
        env = dict(invocation.action.env)
        env.update({str(key): str(value) for key, value in invocation.env_overrides.items()})
        extra_env = invocation.context.settings.get("env")
        if isinstance(extra_env, Mapping):
            env.update({str(key): str(value) for key, value in extra_env.items()})
        return env

    @staticmethod
    def _filter_outputs(
        invocation: ActionInvocation,
        completed: CompletedProcess[str],
        filters: Sequence[str],
    ) -> tuple[list[str], list[str]]:
        """Filter process outputs using tool-defined transformations.

        Args:
            invocation: Invocation containing filtering callbacks.
            completed: Completed process capturing stdout and stderr.
            filters: Additional filter patterns sourced from configuration.

        Returns:
            tuple[list[str], list[str]]: Filtered stdout and stderr lines.
        """
        stdout_text = invocation.action.filter_stdout(completed.stdout, filters)
        stderr_text = invocation.action.filter_stderr(completed.stderr, filters)
        return stdout_text.splitlines(), stderr_text.splitlines()

    @staticmethod
    def _parse_diagnostics(
        invocation: ActionInvocation,
        stdout_lines: Sequence[str],
        stderr_lines: Sequence[str],
    ) -> Sequence[RawDiagnostic | Diagnostic]:
        """Parse diagnostics emitted by the tool invocation.

        Args:
            invocation: Invocation providing parser metadata.
            stdout_lines: Normalised stdout lines from the tool.
            stderr_lines: Normalised stderr lines from the tool.

        Returns:
            Sequence[RawDiagnostic | Diagnostic]: Parsed diagnostics when a parser is available.
        """
        if invocation.action.parser is None:
            return ()
        return invocation.action.parser.parse(
            stdout_lines,
            stderr_lines,
            context=invocation.context,
        )

    @staticmethod
    def _adjust_returncode(
        tool_name: str,
        original_returncode: int,
        diagnostics: Sequence[Diagnostic],
        *,
        ignore_exit: bool = False,
    ) -> int:
        """Return the adjusted exit status for ``tool_name``.

        Args:
            tool_name: Name of the executing tool.
            original_returncode: Exit status reported by the subprocess.
            diagnostics: Diagnostics produced by the parser.

        Returns:
            int: Adjusted return code honoring tool-specific conventions.
        """
        if tool_name == PYLINT_TOOL_NAME and not diagnostics:
            return 0
        if tool_name == TOMBI_TOOL_NAME and not diagnostics:
            return 0
        if ignore_exit and not diagnostics and original_returncode in _IGNORED_CHECK_RETURN_CODES:
            return 0
        return original_returncode


def _log_action_failure(
    *,
    invocation: ActionInvocation,
    completed: CompletedProcess[str],
    diagnostics: Sequence[Diagnostic],
    root: Path,
    from_cache: bool,
) -> None:
    """Emit a structured warning describing a failed tool action."""

    command_repr = _format_command(invocation.command)
    files_repr = _summarize_files(invocation.context.files, root)
    stderr_tail = _last_non_empty_line(_split_output(completed.stderr))
    stdout_tail = _last_non_empty_line(_split_output(completed.stdout))

    details: list[str] = [
        f"command: {command_repr}",
        f"cwd: {root}",
        f"diagnostics: {len(diagnostics)}",
    ]
    if files_repr:
        details.append(f"files: {files_repr}")
    if stderr_tail:
        details.append(f"stderr: {stderr_tail}")
    if stdout_tail:
        details.append(f"stdout: {stdout_tail}")
    if from_cache:
        details.append("source: cache (rerun with --no-cache to re-execute)")

    message = (
        f"{invocation.tool_name}:{invocation.action.name} failed (exit {completed.returncode})"
        + "\n  "
        + "\n  ".join(details)
    )

    cfg = invocation.context.cfg.output
    warn(message, use_emoji=cfg.emoji, use_color=cfg.color)


def _format_command(command: Sequence[str]) -> str:
    """Return a shell-friendly representation of ``command``."""

    return shlex.join(command)


def _summarize_files(files: Sequence[Path], root: Path) -> str | None:
    """Return a compact string summarising target ``files`` relative to *root*."""

    if not files:
        return None
    display: list[str] = []
    for path in files[:5]:
        try:
            display.append(normalize_path_key(path, base_dir=root))
        except ValueError:
            display.append(str(path))
    remaining = len(files) - len(display)
    if remaining > 0:
        display.append(f"… (+{remaining} more)")
    return ", ".join(display)


def _split_output(payload: str | Sequence[str] | None) -> list[str]:
    """Return *payload* as a list of lines."""

    if payload is None:
        return []
    if isinstance(payload, str):
        return payload.splitlines()
    return [str(entry) for entry in payload]


def _last_non_empty_line(lines: Sequence[str]) -> str | None:
    """Return the last non-empty line from ``lines`` truncated for readability."""

    for raw_line in reversed(lines):
        hint = raw_line.strip()
        if hint:
            return shorten(hint, width=160, placeholder="…")
    return None


__all__ = [
    "ActionExecutor",
    "ActionInvocation",
    "ExecutionEnvironment",
    "ExecutionState",
    "FunctionRunner",
    "OutcomeRecord",
    "RunnerCallable",
    "ScheduledAction",
    "wrap_runner",
]
