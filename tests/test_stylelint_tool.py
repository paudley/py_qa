# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Tests for the stylelint tool integration."""

from __future__ import annotations

from pathlib import Path

from pyqa.config import Config
from pyqa.tooling import ToolCatalogLoader
from pyqa.tooling.strategies import command_option_map
from pyqa.tools.base import ToolAction, ToolContext

_PYQA_ROOT = Path(__file__).resolve().parents[1]
_CATALOG_ROOT = _PYQA_ROOT / "tooling" / "catalog"


def _stylelint_config(action: str) -> dict[str, object]:
    loader = ToolCatalogLoader(catalog_root=_CATALOG_ROOT)
    snapshot = loader.load_snapshot()
    for definition in snapshot.tools:
        if definition.name != "stylelint":
            continue
        for candidate in definition.actions:
            if candidate.name == action:
                return dict(candidate.command.reference.config)
    raise AssertionError(
        f"stylelint command configuration for action '{action}' missing from catalog",
    )


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

    builder = command_option_map(_stylelint_config("lint"))
    action = ToolAction(name="lint", command=builder)

    command = action.build_command(ctx)
    assert command[0] == "stylelint"
    assert "--formatter" in command and "json" in command
    assert "--config" in command and str(ctx.settings["config"].resolve()) in command
    assert "--custom-syntax" in command and "postcss-scss" in command
    assert "--quiet" in command
    assert command[-1].endswith("main.css")


def test_stylelint_fix_command_respects_fix_flag(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    builder = command_option_map(_stylelint_config("fix"))
    action = ToolAction(name="fix", command=builder, is_fix=True)

    command = action.build_command(ctx)
    assert command[0] == "stylelint"
    assert "--fix" in command
    assert "--formatter" not in command  # fix mode avoids forcing formatter output
    assert command[-1].endswith("main.css")


def test_stylelint_defaults_max_warnings(tmp_path: Path) -> None:
    cfg = Config()
    cfg.severity.max_warnings = 7
    builder = command_option_map(_stylelint_config("lint"))
    action = ToolAction(name="lint", command=builder)
    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[tmp_path / "styles" / "main.css"],
        settings=cfg.tool_settings.setdefault("stylelint", {}),
    )

    command = action.build_command(ctx)
    assert "--max-warnings" in command and "7" in command

    cfg_none = Config()
    builder_none = command_option_map(_stylelint_config("lint"))
    action_none = ToolAction(name="lint", command=builder_none)
    ctx_none = ToolContext(
        cfg=cfg_none,
        root=tmp_path,
        files=[tmp_path / "styles" / "main.css"],
        settings=cfg_none.tool_settings.setdefault("stylelint", {}),
    )

    command_none = action_none.build_command(ctx_none)
    assert "--max-warnings" not in command_none
