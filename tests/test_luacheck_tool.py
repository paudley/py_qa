# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Tests for luacheck tool integration."""

from __future__ import annotations

from pathlib import Path

from pyqa.config import Config
from pyqa.tooling import ToolCatalogLoader
from pyqa.tooling.strategies import command_option_map
from pyqa.tools.base import ToolAction, ToolContext

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_CATALOG_ROOT = _PROJECT_ROOT / "tooling" / "catalog"


def _luacheck_config() -> dict[str, object]:
    loader = ToolCatalogLoader(catalog_root=_CATALOG_ROOT)
    snapshot = loader.load_snapshot()
    for definition in snapshot.tools:
        if definition.name == "luacheck":
            return dict(definition.actions[0].command.reference.config)
    raise AssertionError("luacheck command configuration missing from catalog")


def test_luacheck_command_build(tmp_path: Path) -> None:
    cfg = Config()
    cfg.execution.line_length = 100
    cfg.complexity.max_complexity = 12
    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[tmp_path / "src" / "module.lua"],
        settings={
            "config": tmp_path / ".luacheckrc",
            "std": "lua54",
            "globals": ["vim"],
            "ignore": ["212"],
            "exclude-files": [tmp_path / "vendor" / ""],
            "args": ["--jobs", "2"],
        },
    )

    builder = command_option_map(_luacheck_config())
    action = ToolAction(name="lint", command=builder)
    command = action.build_command(ctx)

    assert command[0] == "luacheck"
    assert "--formatter" in command and "plain" in command
    assert "--codes" in command and "--no-color" in command
    assert "--max-cyclomatic-complexity" in command and "12" in command
    assert "--max-line-length" in command and "100" in command
    assert command[-1].endswith("module.lua")
