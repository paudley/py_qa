# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Tests for phplint tool integration."""

from __future__ import annotations

from pathlib import Path

from pyqa.config import Config
from pyqa.tools.base import ToolAction, ToolContext
from pyqa.tools.builtins import _PhplintCommand


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

    action = ToolAction(
        name="lint",
        command=_PhplintCommand(base=("phplint",)),
        append_files=True,
    )

    command = action.build_command(ctx)
    assert command[0] == "phplint"
    assert "--no-ansi" in command
    assert "--no-progress" in command
    assert "--configuration" in command
    assert "--include" in command
    assert command[-1].endswith("index.php")
