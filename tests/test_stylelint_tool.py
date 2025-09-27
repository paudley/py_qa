# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Tests for the stylelint tool integration."""

from __future__ import annotations

from pathlib import Path

from pyqa.config import Config
from pyqa.tools.base import ToolAction, ToolContext
from pyqa.tools.builtins import StylelintCommand


def _ctx(tmp_path: Path, **settings) -> ToolContext:
    cfg = Config()
    return ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[tmp_path / "styles" / "main.css"],
        settings=settings,
    )


def test_stylelint_lint_command_includes_formatter_and_paths(tmp_path: Path) -> None:
    ctx = _ctx(
        tmp_path,
        config=tmp_path / "config" / "stylelint.config.js",
        ignore_path=tmp_path / ".stylelintignore",
        custom_syntax="postcss-scss",
        quiet=True,
        max_warnings=5,
    )

    action = ToolAction(
        name="lint",
        command=StylelintCommand(base=("stylelint",)),
        append_files=True,
    )

    command = action.build_command(ctx)
    assert command[0] == "stylelint"
    assert "--formatter" in command
    assert "json" in command
    assert "--config" in command
    assert str(ctx.settings["config"]) in command
    assert command[-1].endswith("main.css")


def test_stylelint_fix_command_respects_fix_flag(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    action = ToolAction(
        name="fix",
        command=StylelintCommand(base=("stylelint", "--fix"), is_fix=True),
        append_files=True,
        is_fix=True,
    )

    command = action.build_command(ctx)
    assert command[0] == "stylelint"
    assert "--fix" in command
    assert "--formatter" not in command  # default formatter not forced for fix mode
    assert command[-1].endswith("main.css")
