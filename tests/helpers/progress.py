"""Helpers for capturing Rich progress output in CLI tests."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Protocol

import pytest


@dataclass(frozen=True)
class ProgressRecord:
    kind: str
    payload: tuple[Any, ...] = ()


@dataclass
class _TaskState:
    description: str
    total: int
    completed: int
    fields: dict[str, Any]


class ProgressInterface(Protocol):
    def start(self) -> None: ...

    def stop(self) -> None: ...

    def add_task(self, description: str, *, total: int = 0, **fields: Any) -> int: ...

    def update(
        self,
        task_id: int,
        *,
        description: str | None = None,
        total: int | None = None,
        **fields: Any,
    ) -> None: ...

    def advance(self, task_id: int, advance: int = 1) -> None: ...

    def get_task(self, task_id: int) -> SimpleNamespace: ...


class ProgressProxy:
    """Minimal Rich.Progress test double that records operations."""

    records: list[ProgressRecord]
    _tasks: dict[int, _TaskState]
    _next_id: int
    _started: bool

    def __init__(
        self,
        *args: object,
        **kwargs: object,
    ) -> None:
        self.records = []
        self._tasks = {}
        self._next_id = 1
        self._started = False

    def __enter__(self) -> ProgressProxy:
        """Return self so the proxy can be used as a context manager."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: object,
    ) -> None:
        """Stop the progress proxy on context exit."""
        self.stop()

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._append("start")

    def stop(self) -> None:
        if not self._started:
            return
        self._started = False
        self._append("stop")

    def add_task(self, description: str, *, total: int = 0, **fields: object) -> int:
        task_id = self._next_id
        self._next_id += 1
        self._tasks[task_id] = _TaskState(
            description=description,
            total=total,
            completed=0,
            fields=dict(fields),
        )
        self._append("add", description, total, dict(fields))
        return task_id

    def update(
        self,
        task_id: int,
        *,
        description: str | None = None,
        total: int | None = None,
        **fields: object,
    ) -> None:
        task = self._tasks[task_id]
        if description is not None:
            task.description = description
        if total is not None:
            task.total = total
        if fields:
            task.fields.update(fields)
        snapshot_fields = dict(task.fields)
        self._append("update", task.description, task.total, snapshot_fields)

    def advance(self, task_id: int, advance: int = 1) -> None:
        task = self._tasks[task_id]
        task.completed = int(task.completed) + advance
        self._append("advance", task.completed)

    def get_task(self, task_id: int) -> SimpleNamespace:
        task = self._tasks[task_id]
        return SimpleNamespace(total=task.total, completed=task.completed)

    def _append(self, kind: str, *payload: Any) -> None:
        self.records.append(ProgressRecord(kind=kind, payload=payload))


class ProgressRecorder:
    """Factory that tracks progress instances created during a test."""

    def __init__(self) -> None:
        self.instances: list[ProgressProxy] = []

    def factory(self, *args: object, **kwargs: object) -> ProgressProxy:
        proxy = ProgressProxy(*args, **kwargs)
        self.instances.append(proxy)
        return proxy

    def require_single_instance(self) -> ProgressProxy:
        assert self.instances, "progress bar should initialise"
        assert len(self.instances) == 1, "expected a single progress instance"
        return self.instances[0]


def install_progress_recorder(
    monkeypatch: pytest.MonkeyPatch,
    *,
    module: object,
    attribute: str = "Progress",
) -> ProgressRecorder:
    """Patch ``module.attribute`` with ProgressRecorder.factory and return the recorder."""
    recorder = ProgressRecorder()
    monkeypatch.setattr(module, attribute, recorder.factory)
    return recorder


def run_with_progress(
    orchestrator: object,
    *,
    plan_tools: Sequence[tuple[str, str]] | None = None,
    hook_adapter: Callable[[object], None] | None = None,
) -> None:
    """Utility hook to drive orchestrator hooks for progress assertions."""
    if (hooks := getattr(orchestrator, "_hooks", None)) is None:
        return
    if plan_tools and hooks.after_plan:
        hooks.after_plan(len(plan_tools))
    if hooks.after_discovery:
        hooks.after_discovery(1)
    if hooks.before_tool and plan_tools:
        for tool, _action in plan_tools:
            hooks.before_tool(tool)
    if hook_adapter:
        hook_adapter(orchestrator)


def maybe_call(callback: Callable[..., object] | None, *args: object) -> None:
    """Invoke *callback* when provided, mirroring orchestrator hook guards."""
    if callback is not None:
        callback(*args)


def assert_progress_record_phases(
    records: Sequence[ProgressRecord],
    *,
    expected_advances: int,
    required_status_fragments: Iterable[str] = (),
) -> None:
    assert any(record.kind == "start" for record in records)

    advances = [record for record in records if record.kind == "advance"]
    assert len(advances) == expected_advances, "unexpected number of progress advances"

    totals = [
        record.payload[1]
        for record in records
        if record.kind == "update"
        and len(record.payload) >= 2
        and isinstance(record.payload[1], int)
    ]
    assert totals, "expected at least one progress total update"

    status_fields = [
        record.payload[2]
        for record in records
        if record.kind == "update"
        and len(record.payload) >= 3
        and isinstance(record.payload[2], dict)
    ]
    status_values = [str(fields.get("current_status", "")) for fields in status_fields]
    for fragment in required_status_fragments:
        assert any(fragment in status for status in status_values)

    assert any(
        record.kind == "update" and record.payload and record.payload[0] == "Linting complete"
        for record in records
    ), "progress should report completion"

    assert any(record.kind == "stop" for record in records)
