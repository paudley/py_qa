# SPDX-License-Identifier: MIT

# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Tests for the pyright strategy."""

from __future__ import annotations

from pathlib import Path

from pyqa.config import Config
from pyqa.tooling import ToolCatalogLoader
from pyqa.tooling.strategies import command_option_map
from pyqa.tools.base import ToolAction, ToolContext

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_CATALOG_ROOT = _PROJECT_ROOT / "tooling" / "catalog"


def _pyright_config() -> dict[str, object]:
    loader = ToolCatalogLoader(catalog_root=_CATALOG_ROOT)
    snapshot = loader.load_snapshot()
    for definition in snapshot.tools:
        if definition.name == "pyright":
            action = definition.actions[0]
            return dict(action.command.reference.config)
    raise AssertionError("pyright command configuration missing from catalog")


def test_pyright_command_build(tmp_path: Path) -> None:
    cfg = Config()
    cfg.execution.python_version = "3.11"
    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[],
        settings={
            "project": tmp_path / "pyrightconfig.json",
            "lib": True,
            "ignore-external": True,
        },
    )

    builder = command_option_map(_pyright_config())
    action = ToolAction(name="type-check", command=builder)

    command = action.build_command(ctx)
    assert command[:2] == ["pyright", "--outputjson"]
    assert "--project" in command and str((tmp_path / "pyrightconfig.json").resolve()) in command
    assert "--lib" in command
    assert "--ignoreexternal" in command
