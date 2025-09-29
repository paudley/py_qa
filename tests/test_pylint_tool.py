# SPDX-License-Identifier: MIT

"""Tests for the pylint strategy."""

from __future__ import annotations

from pathlib import Path

from pyqa.config import Config
from pyqa.tooling import ToolCatalogLoader
from pyqa.tooling.strategies import pylint_command
from pyqa.tools.base import ToolAction, ToolContext

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_CATALOG_ROOT = _PROJECT_ROOT / "tooling" / "catalog"


def _pylint_config() -> dict[str, object]:
    loader = ToolCatalogLoader(catalog_root=_CATALOG_ROOT)
    snapshot = loader.load_snapshot()
    for definition in snapshot.tools:
        if definition.name == "pylint":
            action = definition.actions[0]
            return dict(action.command.reference.config)
    raise AssertionError("pylint command configuration missing from catalog")


def test_pylint_command_build(tmp_path: Path) -> None:
    cfg = Config()
    cfg.execution.line_length = 90
    cfg.complexity.max_complexity = 15
    cfg.complexity.max_arguments = 5
    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[tmp_path / "pkg" / "module.py"],
        settings={
            "config": tmp_path / ".pylintrc",
            "load-plugins": ["custom_plugin"],
            "disable": ["C0114"],
            "fail-under": 9.5,
            "args": ["pkg"],
        },
    )

    builder = pylint_command(_pylint_config())
    action = ToolAction(name="lint", command=builder, append_files=False)

    command = action.build_command(ctx)
    assert command[0] == "pylint"
    assert "--rcfile" in command and str((tmp_path / ".pylintrc").resolve()) in command
    assert "--load-plugins" in command and "custom_plugin" in command
    assert "--disable" in command and "C0114" in command
    assert "--max-line-length" in command and "90" in command
    assert command[-1] == "pkg"
