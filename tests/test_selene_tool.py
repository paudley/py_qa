# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Tests for selene tool integration."""

from __future__ import annotations

from pathlib import Path

from pyqa.catalog import ToolCatalogLoader
from pyqa.catalog.strategies import command_option_map
from pyqa.config import Config
from pyqa.tools.base import ToolAction, ToolContext

_PYQA_ROOT = Path(__file__).resolve().parents[1]
_CATALOG_ROOT = _PYQA_ROOT / "tooling" / "catalog"


def _selene_command_config() -> dict[str, object]:
    loader = ToolCatalogLoader(catalog_root=_CATALOG_ROOT)
    snapshot = loader.load_snapshot()
    for definition in snapshot.tools:
        if definition.name != "selene":
            continue
        for action in definition.actions:
            if action.name != "lint":
                continue
            return dict(action.command.reference.config)
    raise AssertionError("selene command configuration missing from catalog")


def test_selene_command_build(tmp_path: Path) -> None:
    cfg = Config()
    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[tmp_path / "src" / "script.lua"],
        settings={
            "config": tmp_path / "selene.toml",
            "pattern": ["src/**/script.lua"],
            "num-threads": 4,
            "allow-warnings": True,
            "no-exclude": True,
            "color": "Auto",
            "args": ["--project", "workspace"],
        },
    )

    builder = command_option_map(_selene_command_config())
    action = ToolAction(name="lint", command=builder)

    command = action.build_command(ctx)
    assert command[0] == "selene"
    assert "--display-style" in command
    assert "Json2" in command
    assert "--color" in command
    assert "Auto" in command
    assert "--config" in command
    assert "--pattern" in command
    assert "--num-threads" in command
    assert "--allow-warnings" in command
    assert "--no-exclude" in command
    assert command[-1].endswith("script.lua")
