# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Tests for the stylelint tool integration."""

from __future__ import annotations

from pathlib import Path

from pyqa.config import Config
from pyqa.tooling.strategies import command_stylelint
from pyqa.tools.base import ToolAction, ToolContext


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

    builder = command_stylelint({"base": ["stylelint"]})
    action = ToolAction(
        name="lint",
        command=builder,
        append_files=True,
    )

    command = action.build_command(ctx)
    assert command[0] == "stylelint"
    assert "--formatter" in command and "json" in command
    assert "--config" in command and str(ctx.settings["config"]) in command
    assert command[-1].endswith("main.css")


def test_stylelint_fix_command_respects_fix_flag(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    builder = command_stylelint({"base": ["stylelint", "--fix"], "isFix": True})
    action = ToolAction(
        name="fix",
        command=builder,
        append_files=True,
        is_fix=True,
    )

    command = action.build_command(ctx)
    assert command[0] == "stylelint"
    assert "--fix" in command
    assert "--formatter" not in command  # default formatter not forced for fix mode
    assert command[-1].endswith("main.css")
