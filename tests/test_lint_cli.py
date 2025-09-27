# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Smoke tests for lint CLI behaviors."""

from __future__ import annotations

from collections.abc import Iterable
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import click
from typer.main import get_group
from typer.testing import CliRunner

import pyqa.cli.lint as lint_module
from pyqa.cli.app import app
from pyqa.cli.options import LintOptions
from pyqa.cli.typer_ext import primary_option_name
from pyqa.config import Config
from pyqa.models import RunResult, ToolOutcome
from pyqa.tool_env.models import PreparedCommand
from tests.helpers.progress import (
    assert_progress_record_phases,
    install_progress_recorder,
    maybe_call,
)


def test_lint_warns_when_py_qa_path_outside_workspace(tmp_path: Path, monkeypatch) -> None:
    runner = CliRunner()

    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "py_qa").mkdir()

    monkeypatch.chdir(project_root)

    def fake_run_tool_info(tool_name, root, *, cfg=None, console=None):
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
    assert "ready" in result.stdout


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

    assert result.exit_code == 0
    options = captured["options"]
    assert isinstance(options, LintOptions)
    assert options.no_stats is True
    config = captured["config"]
    assert isinstance(config, Config)
    assert config.output.show_stats is False
    assert "stats" not in result.stdout.lower()
    assert "Passed" in result.stdout


def test_concise_mode_renders_progress_status(monkeypatch, tmp_path: Path) -> None:
    runner = CliRunner()
    recorder = install_progress_recorder(monkeypatch, module=lint_module)
    monkeypatch.setattr(lint_module, "is_tty", lambda: True)
    monkeypatch.setattr(lint_module.Orchestrator, "run", _orchestrator_run_with_progress)

    result = runner.invoke(app, _lint_args(tmp_path))

    assert result.exit_code == 0
    progress = recorder.require_single_instance()
    records = progress.records
    assert any(
        record.kind == "update" and record.payload[0].startswith("Linting ruff")
        for record in records
    )
    totals = [
        record.payload[1]
        for record in records
        if record.kind == "update"
        and len(record.payload) >= 2
        and isinstance(record.payload[1], int)
    ]
    assert any(
        total == 4 for total in totals
    ), "progress total should include tool actions and phases"
    assert_progress_record_phases(
        records,
        expected_advances=4,
        required_status_fragments=("queued", "post-processing", "rendering output"),
    )


def _lint_args(tmp_path: Path, extra: Iterable[str] | None = None) -> list[str]:
    args = [
        "lint",
        "--root",
        str(tmp_path),
        "--no-emoji",
    ]
    if extra:
        args.extend(extra)
    return args


def _orchestrator_run_with_progress(self, config: Config, root: Path) -> RunResult:  # noqa: ANN001
    maybe_call(self._hooks.after_discovery, 1)
    maybe_call(self._hooks.before_tool, "ruff")
    outcomes = [_tool_outcome("lint"), _tool_outcome("fix")]
    for outcome in outcomes:
        maybe_call(self._hooks.after_tool, outcome)
    result = RunResult(root=root, files=[], outcomes=outcomes, tool_versions={})
    maybe_call(self._hooks.after_execution, result)
    return result


def _tool_outcome(action: str) -> ToolOutcome:
    return ToolOutcome(
        tool="ruff",
        action=action,
        returncode=0,
        stdout="",
        stderr="",
        diagnostics=[],
    )


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
        option_records.append(((primary_option_name(param), index), record))
    return [record for _, record in sorted(option_records, key=lambda entry: entry[0])]
