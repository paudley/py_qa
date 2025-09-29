# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Tests for checkmake command builder."""

from __future__ import annotations

from pathlib import Path

from pyqa.config import Config
from pyqa.tooling.strategies import checkmake_command
from pyqa.tools.base import ToolContext


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

    builder = checkmake_command({"base": ["checkmake", "lint"]})
    command = list(builder.build(ctx))
    command.extend(str(path) for path in ctx.files)
    assert command[0] == "checkmake"
    assert "--format" in command and "json" in command
    assert "--config" in command
    assert "--ignore" in command
    assert command[-1].endswith("Makefile")
