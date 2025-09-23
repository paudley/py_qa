# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Tests for shfmt tool integration."""

from __future__ import annotations

from pathlib import Path

from pyqa.config import Config
from pyqa.tools.base import ToolAction, ToolContext
from pyqa.tools.builtins import _ShfmtCommand


def test_shfmt_format_command(tmp_path: Path) -> None:
    cfg = Config()
    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[tmp_path / "script.sh"],
        settings={"indent": 4, "simplify": True},
    )

    action = ToolAction(
        name="format",
        command=_ShfmtCommand(base=("shfmt",), is_fix=True),
        append_files=True,
        is_fix=True,
    )

    command = action.build_command(ctx)
    assert command[0] == "shfmt"
    assert "-w" in command
    assert "-i" in command and "4" in command
    assert "-s" in command
    assert command[-1].endswith("script.sh")


def test_shfmt_check_command(tmp_path: Path) -> None:
    cfg = Config()
    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[tmp_path / "script.sh"],
        settings={"language": "bash", "indent-case": True},
    )

    action = ToolAction(
        name="check",
        command=_ShfmtCommand(base=("shfmt",), is_fix=False),
        append_files=True,
    )

    command = action.build_command(ctx)
    assert command[0] == "shfmt"
    assert "-d" in command
    assert "-ln" in command and "bash" in command
    assert "-ci" in command
