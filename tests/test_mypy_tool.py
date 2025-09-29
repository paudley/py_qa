# SPDX-License-Identifier: MIT

"""Tests for the mypy strategy."""

from __future__ import annotations

from pathlib import Path

from pyqa.config import Config
from pyqa.tooling import ToolCatalogLoader
from pyqa.tooling.strategies import mypy_command
from pyqa.tools.base import ToolAction, ToolContext

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_CATALOG_ROOT = _PROJECT_ROOT / "tooling" / "catalog"


def _mypy_config() -> dict[str, object]:
    loader = ToolCatalogLoader(catalog_root=_CATALOG_ROOT)
    snapshot = loader.load_snapshot()
    for definition in snapshot.tools:
        if definition.name == "mypy":
            action = definition.actions[0]
            return dict(action.command.reference.config)
    raise AssertionError("mypy command configuration missing from catalog")


def test_mypy_command_build(tmp_path: Path) -> None:
    cfg = Config()
    cfg.execution.python_version = "3.12"
    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[tmp_path / "src" / "module.py"],
        settings={
            "config": tmp_path / "mypy.ini",
            "strict": True,
            "plugins": ["pydantic.mypy"],
            "args": ["src"],
        },
    )

    builder = mypy_command(_mypy_config())
    action = ToolAction(name="type-check", command=builder, append_files=False)

    command = action.build_command(ctx)
    assert command[0] == "mypy"
    assert "--config-file" in command and str((tmp_path / "mypy.ini").resolve()) in command
    assert "--strict" in command
    assert "--plugin" in command and "pydantic.mypy" in command
    assert command[-1] == "src"
