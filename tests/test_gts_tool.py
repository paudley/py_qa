# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

from __future__ import annotations

from pathlib import Path

from pyqa.config import Config, ExecutionConfig, OutputConfig
from pyqa.tooling.strategies import gts_command
from pyqa.tools.base import ToolContext


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
    builder = gts_command({"base": ["gts", "lint", "--", "--format", "json"]})
    built = list(builder.build(ctx))
    built.extend(str(path) for path in ctx.files)
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
    builder = gts_command({"base": ["gts", "lint", "--", "--format", "json"]})
    built = builder.build(ctx)
    assert "--config" in built
    assert str(config_path) in built
    assert "--project" in built
    assert str(project_path) in built
    assert built[-1] == "--quiet"
