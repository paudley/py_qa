# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Tests for the doctor CLI command."""

from __future__ import annotations

from io import StringIO
from pathlib import Path

from rich.console import Console
from typer.testing import CliRunner

from pyqa.cli.app import app
from pyqa.cli.doctor import run_doctor
from pyqa.cli.utils import (
    ToolAvailability,
    ToolExecutionDetails,
    ToolStatus,
    ToolVersionStatus,
)
from pyqa.config import Config
from pyqa.config_loader import ConfigLoadResult
from pyqa.tools.base import DeferredCommand, Tool, ToolAction
from pyqa.tools.registry import DEFAULT_REGISTRY


def test_doctor_option(monkeypatch) -> None:
    runner = CliRunner()

    def fake_run_doctor(root):
        print(f"doctor invoked for {root}")
        return 0

    monkeypatch.setattr("pyqa.cli._lint_meta.run_doctor", fake_run_doctor)

    result = runner.invoke(app, ["lint", "--doctor"])

    assert result.exit_code == 0
    assert "doctor invoked" in result.stdout


def test_run_doctor_catalog_initializes_registry(monkeypatch, tmp_path: Path) -> None:
    cfg = Config()
    load_result = ConfigLoadResult(config=cfg)

    class FakeLoader:
        def load_with_trace(self, *, strict: bool = False) -> ConfigLoadResult:
            return load_result

    monkeypatch.setattr("pyqa.cli.doctor.ConfigLoader.for_root", lambda root: FakeLoader())

    def fake_initialize_registry(*, registry, catalog_root=None, schema_root=None):
        registry.reset()
        registry.register(
            Tool(
                name="demo",
                phase="lint",
                actions=(
                    ToolAction(
                        name="lint",
                        command=DeferredCommand(("demo",)),
                    ),
                ),
                runtime="binary",
            ),
        )

    monkeypatch.setattr("pyqa.cli.doctor.initialize_registry", fake_initialize_registry)

    def fake_check_tool_status(tool: Tool) -> ToolStatus:
        return ToolStatus(
            name=tool.name,
            notes="",
            availability=ToolAvailability.OK,
            version=ToolVersionStatus(detected=None, minimum=None),
            execution=ToolExecutionDetails(executable=None, path=None, returncode=0),
            raw_output=None,
        )

    monkeypatch.setattr("pyqa.cli.doctor.check_tool_status", fake_check_tool_status)

    buffer = StringIO()
    console = Console(file=buffer, force_terminal=False, color_system=None, emoji=False)

    exit_code = run_doctor(tmp_path, console=console)

    assert exit_code == 0
    output = buffer.getvalue()
    assert "Tooling Status" in output
    DEFAULT_REGISTRY.reset()
