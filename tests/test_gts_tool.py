# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

from __future__ import annotations

from pathlib import Path

from pyqa.config import Config, ExecutionConfig, OutputConfig
from pyqa.tools.base import ToolAction, ToolContext
from pyqa.tools.builtins import GtsCommand


def _context(tmp_path: Path) -> ToolContext:
    cfg = Config()
    cfg.execution = ExecutionConfig()
    cfg.output = OutputConfig()
    return ToolContext(cfg=cfg, root=tmp_path, files=[tmp_path / "src" / "index.ts"], settings={})


def test_gts_command_adds_files_and_json_format(tmp_path: Path) -> None:
    files = [tmp_path / "src" / "index.ts"]
    ctx = ToolContext(
        cfg=Config(),
        root=tmp_path,
        files=files,
        settings={},
    )
    action = ToolAction(
        name="lint",
        command=GtsCommand(base=("gts", "lint", "--", "--format", "json")),
        append_files=True,
    )
    built = action.build_command(ctx)
    assert tuple(built[:5]) == ("gts", "lint", "--", "--format", "json")
    assert built[-1] == str(files[0])


def test_gts_command_with_settings(tmp_path: Path) -> None:
    config_path = tmp_path / "configs" / "eslint.json"
    project_path = tmp_path / "configs" / "tsconfig.json"
    ctx = ToolContext(
        cfg=Config(),
        root=tmp_path,
        files=[],
        settings={"config": config_path, "project": project_path, "args": ["--quiet"]},
    )
    command = GtsCommand(base=("gts", "lint", "--", "--format", "json"))
    built = command.build(ctx)
    assert "--config" in built
    assert str(config_path) in built
    assert "--project" in built
    assert str(project_path) in built
    assert built[-1] == "--quiet"
