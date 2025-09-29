# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Tests for perltidy command builder."""

from __future__ import annotations

from pathlib import Path

from pyqa.config import Config
from pyqa.tooling.strategies import perltidy_command
from pyqa.tools.base import ToolContext


def test_perltidy_format_command(tmp_path: Path) -> None:
    cfg = Config()
    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[tmp_path / "script.pl"],
        settings={"args": ["--indent-columns=4"]},
    )

    builder = perltidy_command({"base": ["perltidy"], "isFix": True})
    cmd = list(builder.build(ctx))
    cmd.extend(str(path) for path in ctx.files)
    assert cmd[0] == "perltidy"
    assert "-b" in cmd
    assert any(item.startswith("-bext") for item in cmd)
    assert "-q" in cmd
    assert cmd[-1].endswith("script.pl")


def test_perltidy_check_command(tmp_path: Path) -> None:
    cfg = Config()
    ctx = ToolContext(cfg=cfg, root=tmp_path, files=[tmp_path / "script.pl"], settings={})

    builder = perltidy_command({"base": ["perltidy"], "isFix": False})
    cmd = list(builder.build(ctx))
    cmd.extend(str(path) for path in ctx.files)
    assert "--check-only" in cmd
