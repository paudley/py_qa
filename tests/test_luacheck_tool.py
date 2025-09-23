# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Tests for luacheck tool integration."""

from __future__ import annotations

from pathlib import Path

from pyqa.config import Config
from pyqa.tools.base import ToolAction, ToolContext
from pyqa.tools.builtins import _LuacheckCommand


def test_luacheck_command_build(tmp_path: Path) -> None:
    cfg = Config()
    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[tmp_path / "src" / "module.lua"],
        settings={
            "config": tmp_path / ".luacheckrc",
            "std": "lua54",
            "globals": ["vim"],
            "ignore": ["212"],
            "exclude-files": [tmp_path / "vendor" / ""],
            "args": ["--jobs", "2"],
        },
    )

    action = ToolAction(
        name="lint",
        command=_LuacheckCommand(base=("luacheck",)),
        append_files=True,
    )

    command = action.build_command(ctx)
    assert command[0] == "luacheck"
    assert "--formatter" in command and "plain" in command
    assert "--codes" in command
    assert "--no-color" in command
    assert command[-1].endswith("module.lua")
