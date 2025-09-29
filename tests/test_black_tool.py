# SPDX-License-Identifier: MIT

# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Tests for Black strategy integration."""

from __future__ import annotations

from pathlib import Path

from pyqa.config import Config
from pyqa.tooling import ToolCatalogLoader
from pyqa.tooling.strategies import command_option_map
from pyqa.tools.base import ToolAction, ToolContext

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_CATALOG_ROOT = _PROJECT_ROOT / "tooling" / "catalog"


def _black_config(action: str) -> dict[str, object]:
    loader = ToolCatalogLoader(catalog_root=_CATALOG_ROOT)
    snapshot = loader.load_snapshot()
    for definition in snapshot.tools:
        if definition.name != "black":
            continue
        for candidate in definition.actions:
            if candidate.name == action:
                return dict(candidate.command.reference.config)
    raise AssertionError(f"black command configuration for action '{action}' missing from catalog")


def test_black_format_command(tmp_path: Path) -> None:
    cfg = Config()
    cfg.execution.line_length = 88
    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[tmp_path / "src" / "module.py"],
        settings={
            "config": tmp_path / "pyproject.toml",
            "preview": True,
            "args": ["src"],
        },
    )

    builder = command_option_map(_black_config("format"))
    action = ToolAction(name="format", command=builder, append_files=False, is_fix=True)

    command = action.build_command(ctx)
    assert command[0] == "black"
    assert "--config" in command and str((tmp_path / "pyproject.toml").resolve()) in command
    assert "--preview" in command
    assert command[-1] == "src"


def test_black_check_command(tmp_path: Path) -> None:
    cfg = Config()
    ctx = ToolContext(cfg=cfg, root=tmp_path, files=[], settings={})

    builder = command_option_map(_black_config("check"))
    action = ToolAction(name="check", command=builder)

    command = action.build_command(ctx)
    assert command[:2] == ["black", "--check"]
