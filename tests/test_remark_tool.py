# SPDX-License-Identifier: MIT

"""Tests for remark-lint tool integration."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

from pyqa.tooling import ToolCatalogLoader
from pyqa.tooling.strategies import command_option_map
from pyqa.tools.base import ToolAction, ToolContext

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_CATALOG_ROOT = _PROJECT_ROOT / "tooling" / "catalog"


def _remark_config(action: str) -> dict[str, object]:
    loader = ToolCatalogLoader(catalog_root=_CATALOG_ROOT)
    snapshot = loader.load_snapshot()
    for definition in snapshot.tools:
        if definition.name != "remark-lint":
            continue
        for candidate in definition.actions:
            if candidate.name == action:
                return dict(candidate.command.reference.config)
    raise AssertionError(f"remark-lint command configuration for action '{action}' missing from catalog")


def test_remark_lint_command_build(tmp_path: Path) -> None:
    cfg = Mock()
    cfg.execution.line_length = 120
    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[tmp_path / "README.md"],
        settings={
            "config": tmp_path / ".remarkrc.json",
            "use": ["remark-lint-ordered-list-marker-style"],
            "setting": ["listItemIndent=one"],
        },
    )

    builder = command_option_map(_remark_config("lint"))
    action = ToolAction(name="lint", command=builder)

    cmd = action.build_command(ctx)
    assert cmd[0] == "remark"
    assert "--report" in cmd and "json" in cmd
    assert "--use" in cmd and "remark-lint-ordered-list-marker-style" in cmd
    assert "--config" in cmd and str((tmp_path / ".remarkrc.json").resolve()) in cmd
    assert cmd[-1].endswith("README.md")


def test_remark_fix_command_build(tmp_path: Path) -> None:
    cfg = Mock()
    cfg.execution.line_length = 120
    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[],
        settings={},
    )

    builder = command_option_map(_remark_config("fix"))
    action = ToolAction(name="fix", command=builder)

    cmd = action.build_command(ctx)
    assert cmd[0] == "remark"
    assert "--output" in cmd
    assert str(tmp_path) in cmd
