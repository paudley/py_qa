# SPDX-License-Identifier: MIT

# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Tests for the tombi strategy."""

from __future__ import annotations

from pathlib import Path

from pyqa.config import Config
from pyqa.tooling import ToolCatalogLoader
from pyqa.tooling.strategies import command_project_scanner
from pyqa.tools.base import ToolAction, ToolContext

_PYQA_ROOT = Path(__file__).resolve().parents[1]
_CATALOG_ROOT = _PYQA_ROOT / "tooling" / "catalog"


def _tombi_config() -> dict[str, object]:
    loader = ToolCatalogLoader(catalog_root=_CATALOG_ROOT)
    snapshot = loader.load_snapshot()
    for definition in snapshot.tools:
        if definition.name == "tombi":
            action = definition.actions[0]
            return dict(action.command.reference.config)
    raise AssertionError("tombi command configuration missing from catalog")


def test_tombi_command_build(tmp_path: Path) -> None:
    cfg = Config()
    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[tmp_path / "pyproject.toml"],
        settings={
            "stdin-filename": tmp_path / "pyproject.toml",
            "offline": True,
            "verbose": 2,
            "no-cache": True,
            "args": ["pyproject.toml"],
        },
    )

    builder = command_project_scanner(_tombi_config())
    action = ToolAction(name="lint", command=builder, append_files=False)

    command = action.build_command(ctx)
    assert command[:2] == ["tombi", "lint"]
    assert "--stdin-filename" in command and str((tmp_path / "pyproject.toml").resolve()) in command
    assert command.count("-v") == 2
    assert "--no-cache" in command
