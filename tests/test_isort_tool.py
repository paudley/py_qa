# SPDX-License-Identifier: MIT

"""Tests for isort strategy integration."""

from __future__ import annotations

from pathlib import Path

from pyqa.config import Config
from pyqa.tooling import ToolCatalogLoader
from pyqa.tooling.strategies import command_option_map
from pyqa.tools.base import ToolAction, ToolContext

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_CATALOG_ROOT = _PROJECT_ROOT / "tooling" / "catalog"


def _isort_config(action: str) -> dict[str, object]:
    loader = ToolCatalogLoader(catalog_root=_CATALOG_ROOT)
    snapshot = loader.load_snapshot()
    for definition in snapshot.tools:
        if definition.name != "isort":
            continue
        for candidate in definition.actions:
            if candidate.name == action:
                return dict(candidate.command.reference.config)
    raise AssertionError(f"isort command configuration for action '{action}' missing from catalog")


def test_isort_sort_command(tmp_path: Path) -> None:
    cfg = Config()
    cfg.execution.line_length = 100
    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[tmp_path / "src" / "module.py"],
        settings={
            "settings-path": tmp_path / "pyproject.toml",
            "src": ["src"],
            "color": False,
        },
    )

    builder = command_option_map(_isort_config("sort"))
    action = ToolAction(name="sort", command=builder, append_files=False)

    command = action.build_command(ctx)
    assert command[0] == "isort"
    assert "--settings-path" in command and str((tmp_path / "pyproject.toml").resolve()) in command
    assert "--profile" in command and "black" in command
    assert "--line-length" in command and "100" in command
    assert "--no-color" in command


def test_isort_check_command(tmp_path: Path) -> None:
    cfg = Config()
    ctx = ToolContext(cfg=cfg, root=tmp_path, files=[], settings={})

    builder = command_option_map(_isort_config("check"))
    action = ToolAction(name="check", command=builder)

    command = action.build_command(ctx)
    assert command[:2] == ["isort", "--check-only"]
