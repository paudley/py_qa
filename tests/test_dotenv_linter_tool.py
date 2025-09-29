# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Tests for dotenv-linter tool integration."""

from __future__ import annotations

from pathlib import Path

from pyqa.config import Config
from pyqa.tooling.strategies import dotenv_linter_command
from pyqa.tools.base import ToolAction, ToolContext


def test_dotenv_linter_command_build(tmp_path: Path) -> None:
    cfg = Config()
    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[tmp_path / "config" / ".env"],
        settings={
            "exclude": [tmp_path / "config" / ".env.local"],
            "skip": ["LowercaseKey"],
            "schema": tmp_path / "schema" / "env.json",
            "recursive": True,
            "args": ["--not-check-updates"],
        },
    )

    builder = dotenv_linter_command({"base": ["dotenv-linter"]})
    action = ToolAction(
        name="lint",
        command=builder,
        append_files=True,
    )

    command = action.build_command(ctx)
    assert command[0] == "dotenv-linter"
    assert "--no-color" in command
    assert "--quiet" in command
    assert "--exclude" in command
    assert "--skip" in command
    assert "--schema" in command
    assert "--recursive" in command
    assert command[-1].endswith(".env")
