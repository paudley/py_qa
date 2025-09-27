# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Tests for Speccy lint tool integration."""

from __future__ import annotations

from pathlib import Path

from pyqa.config import Config
from pyqa.tools.base import ToolAction, ToolContext
from pyqa.tools.builtins import SpeccyCommand


def test_speccy_command_build(tmp_path: Path) -> None:
    cfg = Config()
    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[tmp_path / "openapi.yaml"],
        settings={"ruleset": tmp_path / "ruleset.yaml", "skip": ["no-empty-response"]},
    )

    action = ToolAction(
        name="lint",
        command=SpeccyCommand(base=("speccy", "lint")),
        append_files=True,
    )

    command = action.build_command(ctx)
    assert command[:3] == ["speccy", "lint", "--reporter"]
    assert "json" in command
    assert "--ruleset" in command
    assert "--skip" in command
    assert command[-1].endswith("openapi.yaml")
