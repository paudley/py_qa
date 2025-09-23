"""Tests for tombi tool integration."""

from __future__ import annotations

from pathlib import Path

from pyqa.config import Config
from pyqa.tools.base import ToolAction, ToolContext
from pyqa.tools.builtins import _TombiCommand


def test_tombi_command_build(tmp_path: Path) -> None:
    cfg = Config()
    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[tmp_path / "configs" / "pyproject.toml"],
        settings={
            "stdin-filename": tmp_path / "stdin.toml",
            "offline": True,
            "no-cache": True,
            "verbose": 2,
            "args": ["--schema", "https://example/schema.json"],
        },
    )

    action = ToolAction(
        name="lint",
        command=_TombiCommand(base=("tombi", "lint")),
        append_files=True,
    )

    command = action.build_command(ctx)
    assert command[0] == "tombi"
    assert command[1] == "lint"
    assert "--stdin-filename" in command
    assert "--offline" in command
    assert "--no-cache" in command
    assert command.count("-v") == 2
    assert "--schema" in command
    assert command[-1].endswith("pyproject.toml")
