# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Tests for checkmake command builder."""

from __future__ import annotations

from pathlib import Path

from pyqa.config import Config
from pyqa.tools.base import ToolAction, ToolContext
from pyqa.tools.builtins import CheckmakeCommand


def test_checkmake_command_build(tmp_path: Path) -> None:
    cfg = Config()
    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[tmp_path / "Makefile"],
        settings={
            "config": tmp_path / "checkmake.yml",
            "ignore": ["missing-help-text"],
        },
    )

    action = ToolAction(
        name="lint",
        command=CheckmakeCommand(base=("checkmake", "lint")),
        append_files=True,
    )

    command = action.build_command(ctx)
    assert command[0] == "checkmake"
    assert "--format" in command
    assert "json" in command
    assert "--config" in command
    assert "--ignore" in command
    assert command[-1].endswith("Makefile")
