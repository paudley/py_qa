# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Tests for dockerfilelint tool integration."""

from __future__ import annotations

from pathlib import Path

from pyqa.config import Config
from pyqa.tooling.strategies import dockerfilelint_command
from pyqa.tools.base import ToolContext


def test_dockerfilelint_command_build(tmp_path: Path) -> None:
    cfg = Config()
    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[tmp_path / "Dockerfile"],
        settings={"config": tmp_path / ".dockerfilelintrc"},
    )

    builder = dockerfilelint_command({"base": ["dockerfilelint", "--output", "json"]})
    command = list(builder.build(ctx))
    command.extend(str(path) for path in ctx.files)
    assert command[0] == "dockerfilelint"
    assert "--output" in command and "json" in command
    assert "--config" in command and str(tmp_path / ".dockerfilelintrc") in command
    assert command[-1].endswith("Dockerfile")
