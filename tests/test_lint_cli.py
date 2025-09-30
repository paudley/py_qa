# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Smoke tests for lint CLI behaviors."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any

import click
from typer.main import get_group
from typer.testing import CliRunner

import pyqa.cli.lint as lint_module
from pyqa.cli.app import app
from pyqa.cli.options import LintOptions
from pyqa.cli.typer_ext import _primary_option_name
from pyqa.config import Config
from pyqa.models import RunResult, ToolOutcome
from pyqa.tool_env.models import PreparedCommand


def test_lint_warns_when_py_qa_path_outside_workspace(tmp_path: Path, monkeypatch) -> None:
    runner = CliRunner()

    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "py_qa").mkdir()

    monkeypatch.chdir(project_root)

    def fake_run_tool_info(tool_name, root, *, cfg=None, console=None, catalog_snapshot=None):
        assert tool_name == "ruff"
        return 0

    monkeypatch.setattr("pyqa.cli.lint.run_tool_info", fake_run_tool_info)

    result = runner.invoke(
        app,
        [
            "lint",
            "py_qa",
            "--root",
            str(project_root),
            "--tool-info",
            "ruff",
            "--no-emoji",
        ],
    )

    assert result.exit_code == 0
    assert "'py_qa' directories are skipped" in result.stdout


def test_lint_fetch_all_tools_flag(monkeypatch, tmp_path: Path) -> None:
    runner = CliRunner()

    prepared = PreparedCommand.from_parts(cmd=["demo"], env={}, version="1.2.3", source="local")
    calls: list[tuple] = []

    def fake_fetch(self, cfg, root, callback=None):  # noqa: ANN001
        if callback:
            callback("start", "demo", "lint", 1, 1, None)
            callback("completed", "demo", "lint", 1, 1, None)
        calls.append((cfg, root))
        return [("demo", "lint", prepared, None)]

    monkeypatch.setattr("pyqa.cli.lint.Orchestrator.fetch_all_tools", fake_fetch)
    monkeypatch.setattr("pyqa.cli.lint.is_tty", lambda: False)

    result = runner.invoke(
        app,
        [
            "lint",
            "--fetch-all-tools",
            "--root",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0
    assert calls
    assert "Tool Preparation" in result.stdout
    assert "demo" in result.stdout
    assert "lint" in result.stdout
    assert "Phase" in result.stdout
    assert "ready" in result.stdout


def test_lint_validate_schema_flag(monkeypatch) -> None:
    runner = CliRunner()

    project_root = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(project_root)

    result = runner.invoke(
        app,
        [
            "lint",
            "--validate-schema",
            "--no-color",
            "--no-emoji",
        ],
    )

    assert result.exit_code == 0
    assert "Catalog validation succeeded" in result.stdout


def test_lint_validate_schema_conflicts(monkeypatch) -> None:
    runner = CliRunner()
    project_root = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(project_root)

    result = runner.invoke(
        app,
        [
            "lint",
            "--validate-schema",
            "--doctor",
        ],
    )

    assert result.exit_code != 0
    combined_output = (result.stdout or "") + (result.stderr or "")
    assert "cannot be combined" in combined_output


def test_lint_no_stats_flag(monkeypatch, tmp_path: Path) -> None:
    runner = CliRunner()
    captured: dict[str, Any] = {}

    original_build_config = lint_module.build_config

    def fake_build_config(options):
        captured["options"] = options
        return original_build_config(options)

    def fake_run(self, config, root):  # noqa: ANN001
        captured["config"] = config
        return RunResult(root=root, files=[], outcomes=[], tool_versions={})

    monkeypatch.setattr(lint_module, "build_config", fake_build_config)
    monkeypatch.setattr(lint_module.Orchestrator, "run", fake_run)

    result = runner.invoke(
        app,
        [
            "lint",
            "--root",
            str(tmp_path),
            "--no-color",
            "--no-emoji",
            "--no-stats",
        ],
    )


def test_lint_no_lint_tests_flag(monkeypatch, tmp_path: Path) -> None:
    runner = CliRunner()
    captured: dict[str, Any] = {}

    original_build_config = lint_module.build_config

    def fake_build_config(options):
        captured["options"] = options
        return original_build_config(options)

    def fake_run(self, config, root):  # noqa: ANN001
        captured["config"] = config
        return RunResult(root=root, files=[], outcomes=[], tool_versions={})

    tests_dir = tmp_path / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(lint_module, "build_config", fake_build_config)
    monkeypatch.setattr(lint_module.Orchestrator, "run", fake_run)

    result = runner.invoke(
        app,
        [
            "lint",
            "--root",
            str(tmp_path),
            "--no-lint-tests",
            "--no-color",
            "--no-emoji",
        ],
    )

    assert result.exit_code == 0
    options = captured["options"]
    assert isinstance(options, LintOptions)
    assert Path("tests") in options.exclude
    config = captured["config"]
    assert isinstance(config, Config)
    resolved_tests = (tmp_path / "tests").resolve()
    assert any(path == resolved_tests for path in config.file_discovery.excludes)




def test_lint_meta_normal_applies_defaults(monkeypatch, tmp_path: Path) -> None:
    runner = CliRunner()
    captured: dict[str, Any] = {}

    original_build_config = lint_module.build_config

    def fake_build_config(options):
        captured["options"] = options
        return original_build_config(options)

    def fake_run(self, config, root):  # noqa: ANN001
        captured["config"] = config
        return RunResult(root=root, files=[], outcomes=[], tool_versions={})

    tests_dir = tmp_path / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(lint_module, "build_config", fake_build_config)
    monkeypatch.setattr(lint_module.Orchestrator, "run", fake_run)

    result = runner.invoke(
        app,
        [
            "lint",
            "--root",
            str(tmp_path),
            "-n",
            "normal",
            "--no-color",
            "--no-emoji",
        ],
    )

    assert result.exit_code == 0
    options = captured["options"]
    assert isinstance(options, LintOptions)
    assert options.advice is True
    assert options.use_local_linters is True
    assert options.no_lint_tests is True
    assert options.output_mode == "concise"
    assert Path("tests") in options.exclude
    config = captured["config"]
    assert isinstance(config, Config)
    resolved_tests = (tmp_path / "tests").resolve()
    assert any(path == resolved_tests for path in config.file_discovery.excludes)

def test_concise_mode_renders_progress_status(monkeypatch, tmp_path: Path) -> None:
    runner = CliRunner()

    progress_instances: list[_FakeProgress] = []

    class _FakeProgress:
        def __init__(self, *args, **kwargs) -> None:
            progress_instances.append(self)
            self.records: list[tuple] = []
            self._tasks: dict[int, dict[str, object]] = {}
            self._next_id = 1
            self._started = False

        def start(self) -> None:
            if not self._started:
                self.records.append(("start",))
                self._started = True

        def stop(self) -> None:
            if self._started:
                self.records.append(("stop",))
                self._started = False

        def add_task(self, description: str, *, total: int = 0, **fields: object) -> int:
            task_id = self._next_id
            self._next_id += 1
            self._tasks[task_id] = {
                "description": description,
                "total": total,
                "completed": 0,
                "fields": dict(fields),
            }
            self.records.append(("add", description, total, dict(fields)))
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
                task["description"] = description
            if total is not None:
                task["total"] = total
            if fields:
                task_fields = task["fields"]
                assert isinstance(task_fields, dict)
                task_fields.update(fields)
            snapshot_fields = dict(task["fields"])
            self.records.append(("update", task["description"], task["total"], snapshot_fields))

        def advance(self, task_id: int, advance: int = 1) -> None:
            task = self._tasks[task_id]
            task["completed"] = int(task["completed"]) + advance
            self.records.append(("advance", task["completed"]))

        def get_task(self, task_id: int):
            task = self._tasks[task_id]
            from types import SimpleNamespace

            return SimpleNamespace(
                total=task["total"],
                completed=task["completed"],
            )

    def fake_run(self, config, root):  # noqa: ANN001
        if self._hooks.after_discovery:
            self._hooks.after_discovery(1)
        if self._hooks.before_tool:
            self._hooks.before_tool("ruff")
        outcome_check = ToolOutcome(
            tool="ruff",
            action="lint",
            returncode=0,
            stdout="",
            stderr="",
            diagnostics=[],
        )
        outcome_fix = ToolOutcome(
            tool="ruff",
            action="fix",
            returncode=0,
            stdout="",
            stderr="",
            diagnostics=[],
        )
        if self._hooks.after_tool:
            self._hooks.after_tool(outcome_check)
            self._hooks.after_tool(outcome_fix)
        result = RunResult(
            root=root,
            files=[],
            outcomes=[outcome_check, outcome_fix],
            tool_versions={},
        )
        if self._hooks.after_execution:
            self._hooks.after_execution(result)
        return result

    monkeypatch.setattr(lint_module, "Progress", _FakeProgress)
    monkeypatch.setattr(lint_module, "is_tty", lambda: True)
    monkeypatch.setattr(lint_module.Orchestrator, "run", fake_run)

    result = runner.invoke(
        app,
        [
            "lint",
            "--root",
            str(tmp_path),
            "--no-emoji",
        ],
    )

    assert result.exit_code == 0
    assert progress_instances, "progress bar should initialise"
    records = progress_instances[0].records
    assert any(event[0] == "start" for event in records)
    advances = [event for event in records if event[0] == "advance"]
    assert len(advances) == 4, (
        "two actions plus post-processing and rendering phases should advance"
    )
    assert any(event[0] == "update" and event[2] == 4 for event in records), (
        "progress total should include tool actions and extra phases"
    )
    assert any(event[0] == "update" and event[1].startswith("Linting ruff") for event in records)
    status_updates = [
        event for event in records if event[0] == "update" and isinstance(event[3], dict)
    ]
    status_values = [event[3].get("current_status", "") for event in status_updates]
    assert any("queued" in status for status in status_values)
    assert any("post-processing" in status for status in status_values)
    assert any("rendering output" in status for status in status_values)
    assert any("done" in status for status in status_values), "progress should report completion"
    assert any(event[0] == "stop" for event in records), "progress should stop after completion"


def test_lint_help_options_sorted() -> None:
    lint_cmd = get_group(app).commands["lint"]
    ctx = click.Context(lint_cmd)
    formatter = _RecordingFormatter()
    lint_cmd.format_options(ctx, formatter)  # type: ignore[arg-type]

    options_section = formatter.sections.get("Options")
    assert options_section is not None

    expected = _expected_sorted_options(lint_cmd, ctx)
    assert options_section == expected


class _RecordingFormatter:
    def __init__(self) -> None:
        self.sections: dict[str, list[tuple[str, str]]] = {}
        self._current: str | None = None

    @contextmanager
    def section(self, title: str):
        previous = self._current
        self._current = title
        try:
            yield
        finally:
            self._current = previous

    def write_dl(self, rows: list[tuple[str, str]]) -> None:
        if self._current is None:
            return
        self.sections.setdefault(self._current, []).extend(rows)


def _expected_sorted_options(command, ctx: click.Context) -> list[tuple[str, str]]:
    option_records: list[tuple[tuple[str, int], tuple[str, str]]] = []
    for index, param in enumerate(command.get_params(ctx)):
        if getattr(param, "param_type_name", "") == "argument":
            continue
        record = param.get_help_record(ctx)
        if record is None:
            continue
        option_records.append(((_primary_option_name(param), index), record))
    return [record for _, record in sorted(option_records, key=lambda entry: entry[0])]
