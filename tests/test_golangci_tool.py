# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Tests for golangci-lint command builder."""

from __future__ import annotations

from pathlib import Path

from pyqa.config import Config
from pyqa.tooling import ToolCatalogLoader
from pyqa.tooling.strategies import command_option_map
from pyqa.tools.base import ToolAction, ToolContext

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_CATALOG_ROOT = _PROJECT_ROOT / "tooling" / "catalog"


def _golangci_command_config() -> dict[str, object]:
    loader = ToolCatalogLoader(catalog_root=_CATALOG_ROOT)
    snapshot = loader.load_snapshot()
    for definition in snapshot.tools:
        if definition.name != "golangci-lint":
            continue
        for action in definition.actions:
            if action.name != "lint":
                continue
            return dict(action.command.reference.config)
    raise AssertionError("golangci-lint command configuration missing from catalog")


def test_golangci_command_includes_enable_all(tmp_path: Path) -> None:
    cfg = Config()
    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[tmp_path / "main.go"],
        settings={"disable": ["govet"], "enable": ["gofmt"]},
    )

    builder = command_option_map(_golangci_command_config())
    action = ToolAction(name="lint", command=builder, append_files=False)

    command = action.build_command(ctx)
    assert "--enable-all" in command
    assert "--disable" in command


def test_golangci_respects_disable_enable_all_flag(tmp_path: Path) -> None:
    cfg = Config()
    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[tmp_path / "main.go"],
        settings={"enable-all": False},
    )

    builder = command_option_map(_golangci_command_config())
    action = ToolAction(name="lint", command=builder, append_files=False)

    command = action.build_command(ctx)
    assert "--enable-all" not in command
