# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Tests for phplint tool integration."""

from __future__ import annotations

from pathlib import Path

from pyqa.config import Config
from pyqa.tooling.strategies import phplint_command
from pyqa.tools.base import ToolContext


def test_phplint_command_build(tmp_path: Path) -> None:
    cfg = Config()
    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[tmp_path / "src" / "index.php"],
        settings={
            "configuration": tmp_path / "phplint.json",
            "exclude": [tmp_path / "vendor"],
            "args": ["--include", "src"],
        },
    )

    builder = phplint_command({"base": ["phplint"]})
    command = list(builder.build(ctx))
    command.extend(str(path) for path in ctx.files)
    assert command[0] == "phplint"
    assert "--no-ansi" in command
    assert "--no-progress" in command
    assert "--configuration" in command
    assert "--include" in command
    assert command[-1].endswith("index.php")
