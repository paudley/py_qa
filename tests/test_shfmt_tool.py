# SPDX-License-Identifier: MIT

# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Tests for shfmt strategy integration."""

from __future__ import annotations

from pathlib import Path

from pyqa.catalog import ToolCatalogLoader
from pyqa.catalog.strategies import command_project_scanner
from pyqa.config import Config
from pyqa.tools.base import ToolAction, ToolContext

_PYQA_ROOT = Path(__file__).resolve().parents[1]
_CATALOG_ROOT = _PYQA_ROOT / "tooling" / "catalog"


def _shfmt_config(action: str) -> dict[str, object]:
    loader = ToolCatalogLoader(catalog_root=_CATALOG_ROOT)
    snapshot = loader.load_snapshot()
    for definition in snapshot.tools:
        if definition.name != "shfmt":
            continue
        for candidate in definition.actions:
            if candidate.name == action:
                return dict(candidate.command.reference.config)
    raise AssertionError(f"shfmt command configuration for action '{action}' missing from catalog")


def test_shfmt_format_command(tmp_path: Path) -> None:
    cfg = Config()
    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[tmp_path / "script.sh"],
        settings={"indent": 4, "simplify": True},
    )

    builder = command_project_scanner(_shfmt_config("format"))
    action = ToolAction(name="format", command=builder, append_files=True, is_fix=True)

    command = action.build_command(ctx)
    assert command[0] == "shfmt"
    assert "-w" in command
    assert "-i" in command and "4" in command
    assert "-s" in command
    assert command[-1].endswith("script.sh")


def test_shfmt_check_command(tmp_path: Path) -> None:
    cfg = Config()
    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[tmp_path / "script.sh"],
        settings={"language": "bash", "indent-case": True},
    )

    builder = command_project_scanner(_shfmt_config("check"))
    action = ToolAction(name="check", command=builder, append_files=True)

    command = action.build_command(ctx)
    assert command[0] == "shfmt"
    assert "-d" in command
    assert "-ln" in command and "bash" in command
    assert "-ci" in command
