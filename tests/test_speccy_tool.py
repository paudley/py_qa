# SPDX-License-Identifier: MIT

# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Tests for Speccy strategy integration."""

from __future__ import annotations

from pathlib import Path

from pyqa.config import Config
from pyqa.catalog import ToolCatalogLoader
from pyqa.catalog.strategies import command_option_map
from pyqa.tools.base import ToolAction, ToolContext

_PYQA_ROOT = Path(__file__).resolve().parents[1]
_CATALOG_ROOT = _PYQA_ROOT / "tooling" / "catalog"


def _speccy_config() -> dict[str, object]:
    loader = ToolCatalogLoader(catalog_root=_CATALOG_ROOT)
    snapshot = loader.load_snapshot()
    for definition in snapshot.tools:
        if definition.name == "speccy":
            action = definition.actions[0]
            return dict(action.command.reference.config)
    raise AssertionError("speccy command configuration missing from catalog")


def test_speccy_command_build(tmp_path: Path) -> None:
    ctx = ToolContext(
        cfg=Config(),
        root=tmp_path,
        files=[tmp_path / "openapi.yaml"],
        settings={"ruleset": tmp_path / "rules.yaml", "skip": ["no-empty-servers"]},
    )

    builder = command_option_map(_speccy_config())
    action = ToolAction(name="lint", command=builder)

    command = action.build_command(ctx)
    assert command[:2] == ["speccy", "lint"]
    assert "--reporter" in command and "json" in command
    assert "--ruleset" in command and str((tmp_path / "rules.yaml").resolve()) in command
    assert "--skip" in command and "no-empty-servers" in command
    assert command[-1].endswith("openapi.yaml")
