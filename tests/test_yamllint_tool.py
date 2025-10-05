# SPDX-License-Identifier: MIT

# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Tests for yamllint strategy integration."""

from __future__ import annotations

from pathlib import Path

from pyqa.config import Config
from pyqa.tooling import ToolCatalogLoader
from pyqa.tooling.strategies import command_option_map
from pyqa.tools.base import ToolAction, ToolContext

_PYQA_ROOT = Path(__file__).resolve().parents[1]
_CATALOG_ROOT = _PYQA_ROOT / "tooling" / "catalog"


def _yamllint_config() -> dict[str, object]:
    loader = ToolCatalogLoader(catalog_root=_CATALOG_ROOT)
    snapshot = loader.load_snapshot()
    for definition in snapshot.tools:
        if definition.name == "yamllint":
            action = definition.actions[0]
            return dict(action.command.reference.config)
    raise AssertionError("yamllint command configuration missing from catalog")


def test_yamllint_command_build(tmp_path: Path) -> None:
    cfg = Config()
    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[tmp_path / "config.yaml"],
        settings={
            "config-file": tmp_path / "yamllint.yaml",
            "strict": True,
            "args": ["config.yaml"],
        },
    )

    builder = command_option_map(_yamllint_config())
    action = ToolAction(name="lint", command=builder, append_files=True)

    command = action.build_command(ctx)
    assert command[0] == "yamllint"
    assert "--config-file" in command and str((tmp_path / "yamllint.yaml").resolve()) in command
    assert "--strict" in command
    assert command[-1].endswith("config.yaml")
