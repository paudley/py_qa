# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Tests for perlcritic command builder."""

from __future__ import annotations

from pathlib import Path

from pyqa.config import Config
from pyqa.tooling import ToolCatalogLoader
from pyqa.tooling.strategies import command_option_map
from pyqa.tools.base import ToolAction, ToolContext

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_CATALOG_ROOT = _PROJECT_ROOT / "tooling" / "catalog"


def _perlcritic_config() -> dict[str, object]:
    loader = ToolCatalogLoader(catalog_root=_CATALOG_ROOT)
    snapshot = loader.load_snapshot()
    for definition in snapshot.tools:
        if definition.name == "perlcritic":
            return dict(definition.actions[0].command.reference.config)
    raise AssertionError("perlcritic command configuration missing from catalog")


def test_perlcritic_command_build(tmp_path: Path) -> None:
    cfg = Config()
    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[tmp_path / "lib" / "Module.pm"],
        settings={"severity": 3, "profile": tmp_path / ".perlcriticrc"},
    )

    builder = command_option_map(_perlcritic_config())
    action = ToolAction(name="lint", command=builder)
    cmd = action.build_command(ctx)

    assert cmd[0] == "perlcritic"
    assert "--nocolor" in cmd
    assert "--verbose" in cmd and "%f:%l:%c:%m (%p)" in cmd
    assert "--profile" in cmd and str((tmp_path / ".perlcriticrc").resolve()) in cmd
    assert "--severity" in cmd and "3" in cmd
    assert cmd[-1].endswith("Module.pm")
