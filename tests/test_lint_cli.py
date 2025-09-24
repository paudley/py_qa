# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Smoke tests for lint CLI behaviors."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from pyqa.cli.app import app
from pyqa.tool_env.models import PreparedCommand


def test_lint_warns_when_py_qa_path_outside_workspace(
    tmp_path: Path, monkeypatch
) -> None:
    runner = CliRunner()

    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "py_qa").mkdir()

    monkeypatch.chdir(project_root)

    def fake_run_tool_info(tool_name, root):
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

    prepared = PreparedCommand.from_parts(
        cmd=["demo"], env={}, version="1.2.3", source="local"
    )
    calls: list[tuple] = []

    def fake_fetch(self, cfg, root):  # noqa: ANN001
        calls.append((cfg, root))
        return [("demo", "lint", prepared)]

    monkeypatch.setattr("pyqa.cli.lint.Orchestrator.fetch_all_tools", fake_fetch)

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
    assert "demo:lint ready" in result.stdout
