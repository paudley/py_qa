# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Tests for perltidy command builder."""

from __future__ import annotations

from pathlib import Path

from pyqa.config import Config
from pyqa.tools.base import ToolAction, ToolContext
from pyqa.tools.builtins import PerltidyCommand


def test_perltidy_format_command(tmp_path: Path) -> None:
    cfg = Config()
    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[tmp_path / "script.pl"],
        settings={"args": ["--indent-columns=4"]},
    )

    action = ToolAction(
        name="format",
        command=PerltidyCommand(base=("perltidy",), is_fix=True),
        append_files=True,
        is_fix=True,
    )

    cmd = action.build_command(ctx)
    assert cmd[0] == "perltidy"
    assert "-b" in cmd
    assert any(item.startswith("-bext") for item in cmd)
    assert "-q" in cmd
    assert cmd[-1].endswith("script.pl")


def test_perltidy_check_command(tmp_path: Path) -> None:
    cfg = Config()
    ctx = ToolContext(cfg=cfg, root=tmp_path, files=[tmp_path / "script.pl"], settings={})

    action = ToolAction(
        name="check",
        command=PerltidyCommand(base=("perltidy",), is_fix=False),
        append_files=True,
    )

    cmd = action.build_command(ctx)
    assert "--check-only" in cmd
