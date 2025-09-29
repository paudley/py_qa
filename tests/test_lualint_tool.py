# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Tests for lualint tool integration."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from pyqa.config import Config
from pyqa.tooling import ToolCatalogLoader
from pyqa.tooling.strategies import command_download_binary
from pyqa.tools.base import ToolAction, ToolContext

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_CATALOG_ROOT = _PROJECT_ROOT / "tooling" / "catalog"


def _lualint_config() -> dict[str, object]:
    loader = ToolCatalogLoader(catalog_root=_CATALOG_ROOT)
    snapshot = loader.load_snapshot()
    for definition in snapshot.tools:
        if definition.name == "lualint":
            return dict(definition.actions[0].command.reference.config)
    raise AssertionError("lualint command configuration missing from catalog")


def test_lualint_command_build(tmp_path: Path) -> None:
    cfg = Config()
    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[tmp_path / "src" / "module.lua"],
        settings={"relaxed": True},
    )

    with patch(
        "pyqa.tooling.strategies._download_artifact_for_tool",
        return_value=tmp_path / "cache" / "lualint.lua",
    ):
        builder = command_download_binary(_lualint_config())
        action = ToolAction(name="lint", command=builder)
        command = action.build_command(ctx)

    assert command[0] == "lua"
    assert any(part.endswith("lualint.lua") for part in command)
    assert "-r" in command
    assert command[-1].endswith("module.lua")
