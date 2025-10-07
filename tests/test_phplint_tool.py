# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Tests for phplint tool integration."""

from __future__ import annotations

from pathlib import Path

from pyqa.catalog import ToolCatalogLoader
from pyqa.catalog.strategies import command_option_map
from pyqa.config import Config
from pyqa.tools.base import ToolAction, ToolContext

_PYQA_ROOT = Path(__file__).resolve().parents[1]
_CATALOG_ROOT = _PYQA_ROOT / "tooling" / "catalog"


def _phplint_config() -> dict[str, object]:
    loader = ToolCatalogLoader(catalog_root=_CATALOG_ROOT)
    snapshot = loader.load_snapshot()
    for definition in snapshot.tools:
        if definition.name == "phplint":
            return dict(definition.actions[0].command.reference.config)
    raise AssertionError("phplint command configuration missing from catalog")


def test_phplint_command_build(tmp_path: Path) -> None:
    cfg = Config()
    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[tmp_path / "src" / "index.php"],
        settings={
            "configuration": tmp_path / "phplint.json",
            "exclude": [tmp_path / "vendor"],
            "args": ["--include", "src"],
        },
    )

    builder = command_option_map(_phplint_config())
    action = ToolAction(name="lint", command=builder)
    command = action.build_command(ctx)

    assert command[0] == "phplint"
    assert "--no-ansi" in command
    assert "--no-progress" in command
    assert "--configuration" in command and str((tmp_path / "phplint.json").resolve()) in command
    assert "--include" in command
    assert command[-1].endswith("index.php")
