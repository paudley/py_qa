# SPDX-License-Identifier: MIT

# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Tests for the Prettier command strategy."""

from __future__ import annotations

from pathlib import Path

from pyqa.config import Config
from pyqa.catalog import ToolCatalogLoader
from pyqa.catalog.strategies import command_option_map
from pyqa.tools.base import ToolAction, ToolContext

_PYQA_ROOT = Path(__file__).resolve().parents[1]
_CATALOG_ROOT = _PYQA_ROOT / "tooling" / "catalog"


def _prettier_command_config(action: str) -> dict[str, object]:
    loader = ToolCatalogLoader(catalog_root=_CATALOG_ROOT)
    snapshot = loader.load_snapshot()
    for definition in snapshot.tools:
        if definition.name != "prettier":
            continue
        for candidate in definition.actions:
            if candidate.name == action:
                return dict(candidate.command.reference.config)
    raise AssertionError(
        f"prettier command configuration for action '{action}' missing from catalog",
    )


def test_prettier_format_command_build(tmp_path: Path) -> None:
    cfg = Config()
    cfg.execution.line_length = 88
    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[tmp_path / "src" / "component.tsx"],
        settings={
            "config": tmp_path / "prettier.config.js",
            "plugin": ["@prettier/plugin-xml"],
            "single-quote": True,
            "semi": False,
            "args": ["src"],
        },
    )

    builder = command_option_map(_prettier_command_config("format"))
    action = ToolAction(name="format", command=builder, append_files=False)

    command = action.build_command(ctx)
    assert command[:2] == ["prettier", "--write"]
    assert "--config" in command and str((tmp_path / "prettier.config.js").resolve()) in command
    assert "--plugin" in command and "@prettier/plugin-xml" in command
    assert "--single-quote" in command
    assert "--no-semi" in command
    assert "--print-width" in command and "88" in command
    assert command[-1] == "src"


def test_prettier_check_command_build(tmp_path: Path) -> None:
    cfg = Config()
    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[],
        settings={},
    )

    builder = command_option_map(_prettier_command_config("check"))
    action = ToolAction(name="check", command=builder)

    command = action.build_command(ctx)
    assert command[:2] == ["prettier", "--check"]
