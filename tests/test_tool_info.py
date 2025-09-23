# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Tests for the tool-info CLI command."""

from __future__ import annotations

from typer.testing import CliRunner

from pyqa.cli.app import app


def test_tool_info_option(monkeypatch) -> None:
    runner = CliRunner()

    def fake_run_tool_info(tool_name, root):
        print(f"tool info for {tool_name} at {root}")
        return 0

    monkeypatch.setattr("pyqa.cli.lint.run_tool_info", fake_run_tool_info)

    result = runner.invoke(app, ["lint", "--tool-info", "ruff"])

    assert result.exit_code == 0
    assert "tool info for ruff" in result.stdout
