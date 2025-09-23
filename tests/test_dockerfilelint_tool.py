"""Tests for dockerfilelint tool integration."""

from __future__ import annotations

from pathlib import Path

from pyqa.config import Config
from pyqa.tools.base import ToolAction, ToolContext
from pyqa.tools.builtins import _DockerfilelintCommand


def test_dockerfilelint_command_build(tmp_path: Path) -> None:
    cfg = Config()
    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[tmp_path / "Dockerfile"],
        settings={"config": tmp_path / ".dockerfilelintrc"},
    )

    action = ToolAction(
        name="lint",
        command=_DockerfilelintCommand(base=("dockerfilelint", "--output", "json")),
        append_files=True,
    )

    command = action.build_command(ctx)
    assert command[0] == "dockerfilelint"
    assert "--output" in command and "json" in command
    assert "--config" in command and str(tmp_path / ".dockerfilelintrc") in command
    assert command[-1].endswith("Dockerfile")
