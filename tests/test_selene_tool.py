# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Tests for selene tool integration."""

from __future__ import annotations

from pathlib import Path

from pyqa.config import Config
from pyqa.tools.base import ToolAction, ToolContext
from pyqa.tools.builtins import _SeleneCommand


def test_selene_command_build(tmp_path: Path) -> None:
    cfg = Config()
    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[tmp_path / "src" / "script.lua"],
        settings={
            "config": tmp_path / "selene.toml",
            "pattern": ["src/**/script.lua"],
            "num-threads": 4,
            "allow-warnings": True,
            "no-exclude": True,
            "color": "Auto",
            "args": ["--project", "workspace"],
        },
    )

    action = ToolAction(
        name="lint",
        command=_SeleneCommand(base=("selene",)),
        append_files=True,
    )

    command = action.build_command(ctx)
    assert command[0] == "selene"
    assert "--display-style" in command
    assert "Json2" in command
    assert "--color" in command
    assert "Auto" in command
    assert "--config" in command
    assert "--pattern" in command
    assert "--num-threads" in command
    assert "--allow-warnings" in command
    assert "--no-exclude" in command
    assert command[-1].endswith("script.lua")
