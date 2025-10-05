# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Tests for dockerfilelint tool integration."""

from __future__ import annotations

from pathlib import Path

from pyqa.config import Config
from pyqa.catalog import ToolCatalogLoader
from pyqa.catalog.strategies import command_option_map
from pyqa.tools.base import ToolAction, ToolContext

_PYQA_ROOT = Path(__file__).resolve().parents[1]
_CATALOG_ROOT = _PYQA_ROOT / "tooling" / "catalog"


def _dockerfilelint_config() -> dict[str, object]:
    loader = ToolCatalogLoader(catalog_root=_CATALOG_ROOT)
    snapshot = loader.load_snapshot()
    for definition in snapshot.tools:
        if definition.name == "dockerfilelint":
            return dict(definition.actions[0].command.reference.config)
    raise AssertionError("dockerfilelint command configuration missing from catalog")


def test_dockerfilelint_command_build(tmp_path: Path) -> None:
    cfg = Config()
    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[tmp_path / "Dockerfile"],
        settings={"config": tmp_path / ".dockerfilelintrc"},
    )

    builder = command_option_map(_dockerfilelint_config())
    action = ToolAction(name="lint", command=builder)
    command = action.build_command(ctx)

    assert command[0] == "dockerfilelint"
    assert "--output" in command and "json" in command
    assert "--config" in command and str((tmp_path / ".dockerfilelintrc").resolve()) in command
    assert command[-1].endswith("Dockerfile")
