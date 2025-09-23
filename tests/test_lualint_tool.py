"""Tests for lualint tool integration."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from pyqa.config import Config
from pyqa.tools.base import ToolAction, ToolContext
from pyqa.tools.builtins import _LualintCommand


def test_lualint_command_build(tmp_path: Path) -> None:
    cfg = Config()
    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[tmp_path / "src" / "module.lua"],
        settings={"relaxed": True},
    )

    with patch("pyqa.tools.builtins._ensure_lualint", return_value=tmp_path / "cache" / "lualint"):
        action = ToolAction(
            name="lint",
            command=_LualintCommand(base=("lua",)),
            append_files=True,
        )
        command = action.build_command(ctx)

    assert command[0] == "lua"
    assert "-r" in command
    assert command[-1].endswith("module.lua")
