# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Tests for yamllint tool integration."""

from __future__ import annotations

from pathlib import Path

from pyqa.config import Config
from pyqa.tools.base import ToolAction, ToolContext
from pyqa.tools.builtins import _YamllintCommand


def _ctx(tmp_path: Path, **settings) -> ToolContext:
    cfg = Config()
    return ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[tmp_path / "configs" / "app.yaml"],
        settings=settings,
    )


def test_yamllint_command_includes_json_format(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, **{"config-file": tmp_path / ".yamllint"})
    action = ToolAction(
        name="lint",
        command=_YamllintCommand(base=("yamllint",)),
        append_files=True,
    )

    command = action.build_command(ctx)
    assert command[0] == "yamllint"
    assert "--format" in command and "parsable" in command
    assert "--config-file" in command
    assert command[-1].endswith("app.yaml")


def test_yamllint_allows_strict_flag(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, strict=True, args=["--no-warnings"])
    action = ToolAction(
        name="lint",
        command=_YamllintCommand(base=("yamllint",)),
        append_files=True,
    )

    command = action.build_command(ctx)
    assert "--strict" in command
    assert "--no-warnings" in command
