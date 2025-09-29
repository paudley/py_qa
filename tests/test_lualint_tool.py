# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Tests for lualint tool integration."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from pyqa.config import Config
from pyqa.tooling.strategies import lualint_command
from pyqa.tools.base import ToolContext


def test_lualint_command_build(tmp_path: Path) -> None:
    cfg = Config()
    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[tmp_path / "src" / "module.lua"],
        settings={"relaxed": True},
    )

    with patch(
        "pyqa.tooling.strategies._download_artifact_for_tool",
        return_value=tmp_path / "cache" / "lualint",
    ):
        builder = lualint_command({"base": ["lua"], "download": {}})
        command = list(builder.build(ctx))
        command.extend(str(path) for path in ctx.files)

    assert command[0] == "lua"
    assert "-r" in command
    assert command[-1].endswith("module.lua")
