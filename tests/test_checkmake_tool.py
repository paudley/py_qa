# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Tests for checkmake command builder."""

from __future__ import annotations

from pathlib import Path

from pyqa.catalog import ToolCatalogLoader
from pyqa.catalog.strategies import command_option_map
from pyqa.config import Config
from pyqa.tools.base import ToolAction, ToolContext

_PYQA_ROOT = Path(__file__).resolve().parents[1]
_CATALOG_ROOT = _PYQA_ROOT / "tooling" / "catalog"


def _checkmake_config() -> dict[str, object]:
    loader = ToolCatalogLoader(catalog_root=_CATALOG_ROOT)
    snapshot = loader.load_snapshot()
    for definition in snapshot.tools:
        if definition.name == "checkmake":
            return dict(definition.actions[0].command.reference.config)
    raise AssertionError("checkmake command configuration missing from catalog")


def test_checkmake_command_build(tmp_path: Path) -> None:
    cfg = Config()
    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[tmp_path / "Makefile"],
        settings={
            "config": tmp_path / "checkmake.yml",
            "ignore": ["missing-help-text"],
        },
    )

    builder = command_option_map(_checkmake_config())
    action = ToolAction(name="lint", command=builder)
    command = action.build_command(ctx)

    assert command[0] == "checkmake"
    assert "--format" in command and "json" in command
    assert "--config" in command and str((tmp_path / "checkmake.yml").resolve()) in command
    assert "--ignore" in command and "missing-help-text" in command
    assert command[-1].endswith("Makefile")
