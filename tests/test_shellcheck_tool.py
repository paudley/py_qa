# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Tests for shellcheck catalog definition."""

from __future__ import annotations

from pathlib import Path

from pyqa.catalog import ToolCatalogLoader
from pyqa.catalog.strategies import command_option_map
from pyqa.config import Config
from pyqa.tools.base import ToolAction, ToolContext

_PYQA_ROOT = Path(__file__).resolve().parents[1]
_CATALOG_ROOT = _PYQA_ROOT / "tooling" / "catalog"


def _shellcheck_config() -> dict[str, object]:
    loader = ToolCatalogLoader(catalog_root=_CATALOG_ROOT)
    snapshot = loader.load_snapshot()
    for definition in snapshot.tools:
        if definition.name != "shellcheck":
            continue
        for action in definition.actions:
            if action.name == "lint":
                return dict(action.command.reference.config)
    raise AssertionError("shellcheck lint action missing from catalog")


def test_shellcheck_command(tmp_path: Path) -> None:
    ctx = ToolContext(
        cfg=Config(),
        root=tmp_path,
        files=[tmp_path / "script.sh"],
        settings={
            "severity": "error",
            "exclude": ["SC1000", "SC2000"],
            "external-sources": True,
            "shell": "bash",
        },
    )
    builder = command_option_map(_shellcheck_config())
    action = ToolAction(name="lint", command=builder)

    command = action.build_command(ctx)
    assert command[:3] == ["shellcheck", "--color=never", "--format=json"]
    assert "--severity=error" in command
    assert "--exclude" in command
    exclude_idx = command.index("--exclude")
    assert "SC1000" in command[exclude_idx + 1]
    assert "--external-sources" in command
    assert "--shell=bash" in command
    assert str(ctx.files[0]) in command
