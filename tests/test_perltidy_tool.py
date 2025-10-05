# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Tests for perltidy command builder."""

from __future__ import annotations

from pathlib import Path

from pyqa.config import Config
from pyqa.tooling import ToolCatalogLoader
from pyqa.tooling.strategies import command_option_map
from pyqa.tools.base import ToolAction, ToolContext

_PYQA_ROOT = Path(__file__).resolve().parents[1]
_CATALOG_ROOT = _PYQA_ROOT / "tooling" / "catalog"


def _perltidy_config(action: str) -> dict[str, object]:
    loader = ToolCatalogLoader(catalog_root=_CATALOG_ROOT)
    snapshot = loader.load_snapshot()
    for definition in snapshot.tools:
        if definition.name != "perltidy":
            continue
        for candidate in definition.actions:
            if candidate.name == action:
                return dict(candidate.command.reference.config)
    raise AssertionError(
        f"perltidy command configuration for action '{action}' missing from catalog",
    )


def test_perltidy_format_command(tmp_path: Path) -> None:
    cfg = Config()
    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[tmp_path / "script.pl"],
        settings={"args": ["--indent-columns=4"]},
    )

    builder = command_option_map(_perltidy_config("format"))
    action = ToolAction(name="format", command=builder, is_fix=True)
    cmd = action.build_command(ctx)
    assert cmd[0] == "perltidy"
    assert "-b" in cmd and any(item.startswith('-bext=""') for item in cmd)
    assert "-q" in cmd
    assert cmd[-1].endswith("script.pl")


def test_perltidy_check_command(tmp_path: Path) -> None:
    cfg = Config()
    ctx = ToolContext(cfg=cfg, root=tmp_path, files=[tmp_path / "script.pl"], settings={})

    builder = command_option_map(_perltidy_config("check"))
    action = ToolAction(name="check", command=builder)
    cmd = action.build_command(ctx)
    assert "--check-only" in cmd
    assert "-q" in cmd
