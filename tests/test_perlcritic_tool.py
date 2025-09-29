# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Tests for perlcritic command builder."""

from __future__ import annotations

from pathlib import Path

from pyqa.config import Config
from pyqa.tooling.strategies import perlcritic_command
from pyqa.tools.base import ToolContext


def test_perlcritic_command_build(tmp_path: Path) -> None:
    cfg = Config()
    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[tmp_path / "lib" / "Module.pm"],
        settings={"severity": 3, "profile": tmp_path / ".perlcriticrc"},
    )

    builder = perlcritic_command({"base": ["perlcritic"]})
    cmd = list(builder.build(ctx))
    cmd.extend(str(path) for path in ctx.files)
    assert cmd[0] == "perlcritic"
    assert "--nocolor" in cmd
    assert "--verbose" in cmd
    assert "--profile" in cmd
    assert "--severity" in cmd and "3" in cmd
    assert cmd[-1].endswith("Module.pm")
