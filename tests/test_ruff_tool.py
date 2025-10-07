# SPDX-License-Identifier: MIT

# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Tests for ruff strategy integration."""

from __future__ import annotations

from pathlib import Path

from pyqa.catalog import ToolCatalogLoader
from pyqa.catalog.strategies import command_option_map
from pyqa.config import Config
from pyqa.tools.base import ToolAction, ToolContext

_PYQA_ROOT = Path(__file__).resolve().parents[1]
_CATALOG_ROOT = _PYQA_ROOT / "tooling" / "catalog"


def _ruff_config(action: str) -> dict[str, object]:
    loader = ToolCatalogLoader(catalog_root=_CATALOG_ROOT)
    snapshot = loader.load_snapshot()
    for definition in snapshot.tools:
        if definition.name != "ruff":
            continue
        for candidate in definition.actions:
            if candidate.name == action:
                return dict(candidate.command.reference.config)
    raise AssertionError(f"ruff command configuration for action '{action}' missing from catalog")


def _ruff_format_config() -> dict[str, object]:
    loader = ToolCatalogLoader(catalog_root=_CATALOG_ROOT)
    snapshot = loader.load_snapshot()
    for definition in snapshot.tools:
        if definition.name == "ruff-format":
            action = definition.actions[0]
            return dict(action.command.reference.config)
    raise AssertionError("ruff-format command configuration missing from catalog")


def test_ruff_lint_command(tmp_path: Path) -> None:
    cfg = Config()
    cfg.execution.line_length = 120
    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[tmp_path / "src" / "module.py"],
        settings={"preview": True, "args": ["src"]},
    )

    builder = command_option_map(_ruff_config("lint"))
    action = ToolAction(name="lint", command=builder, append_files=False)

    command = action.build_command(ctx)
    assert command[:2] == ["ruff", "check"]
    assert "--preview" in command
    assert "--line-length" in command and "120" in command
    assert command[-1] == "src"


def test_ruff_format_command(tmp_path: Path) -> None:
    cfg = Config()
    cfg.execution.line_length = 99
    ctx = ToolContext(cfg=cfg, root=tmp_path, files=[], settings={})

    builder = command_option_map(_ruff_format_config())
    action = ToolAction(name="format", command=builder)

    command = action.build_command(ctx)
    assert command[:2] == ["ruff", "format"]
    assert "--line-length" in command and "99" in command
