# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Tests for the tool-info CLI command."""

from __future__ import annotations

from io import StringIO
from pathlib import Path

from rich.console import Console
from typer.testing import CliRunner

from pyqa.cli.app import app
from pyqa.cli.tool_info import run_tool_info


def test_tool_info_option(monkeypatch) -> None:
    runner = CliRunner()

    def fake_run_tool_info(tool_name, root, *, cfg=None, console=None):
        print(f"tool info for {tool_name} at {root}")
        return 0

    monkeypatch.setattr("pyqa.cli.lint.run_tool_info", fake_run_tool_info)

    result = runner.invoke(app, ["lint", "--tool-info", "ruff"])

    assert result.exit_code == 0
    assert "tool info for ruff" in result.stdout


def test_run_tool_info_includes_mypy_defaults(tmp_path: Path) -> None:
    buffer = StringIO()
    console = Console(file=buffer, force_terminal=False, color_system=None, emoji=False)

    exit_code = run_tool_info("mypy", root=tmp_path, console=console)

    assert exit_code == 0
    output = buffer.getvalue()
    assert "--strict" in output
    assert "--warn-unused-ignores" in output
    assert "--show-error-codes" in output


def test_run_tool_info_includes_pylint_plugins(tmp_path: Path) -> None:
    buffer = StringIO()
    console = Console(file=buffer, force_terminal=False, color_system=None, emoji=False)

    exit_code = run_tool_info("pylint", root=tmp_path, console=console)

    assert exit_code == 0
    output = buffer.getvalue()
    assert "--load-plugins" in output
    assert "pylint.extensions.docparams" in output
    assert "--max-complexity" in output
