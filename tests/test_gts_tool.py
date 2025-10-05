# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

from __future__ import annotations

from pathlib import Path

from pyqa.config import Config, ExecutionConfig, OutputConfig
from pyqa.catalog import ToolCatalogLoader
from pyqa.catalog.strategies import command_option_map
from pyqa.tools.base import ToolAction, ToolContext

_PYQA_ROOT = Path(__file__).resolve().parents[1]
_CATALOG_ROOT = _PYQA_ROOT / "tooling" / "catalog"


def _gts_config(action: str) -> dict[str, object]:
    loader = ToolCatalogLoader(catalog_root=_CATALOG_ROOT)
    snapshot = loader.load_snapshot()
    for definition in snapshot.tools:
        if definition.name != "gts":
            continue
        for candidate in definition.actions:
            if candidate.name == action:
                return dict(candidate.command.reference.config)
    raise AssertionError(f"gts command configuration for action '{action}' missing from catalog")


def _context(tmp_path: Path) -> ToolContext:
    cfg = Config()
    cfg.execution = ExecutionConfig()
    cfg.output = OutputConfig()
    return ToolContext(cfg=cfg, root=tmp_path, files=[tmp_path / "src" / "index.ts"], settings={})


def test_gts_command_adds_files_and_json_format(tmp_path: Path) -> None:
    ctx = _context(tmp_path)
    builder = command_option_map(_gts_config("lint"))
    action = ToolAction(name="lint", command=builder)

    command = action.build_command(ctx)
    assert tuple(command[:5]) == ("gts", "lint", "--", "--format", "json")
    assert command[-1].endswith("index.ts")


def test_gts_command_with_settings(tmp_path: Path) -> None:
    config_path = tmp_path / "configs" / "eslint.json"
    project_path = tmp_path / "configs" / "tsconfig.json"
    ctx = ToolContext(
        cfg=Config(),
        root=tmp_path,
        files=[],
        settings={"config": config_path, "project": project_path, "args": ["--quiet"]},
    )
    builder = command_option_map(_gts_config("lint"))
    command = builder.build(ctx)
    assert "--config" in command and str(config_path.resolve()) in command
    assert "--project" in command and str(project_path.resolve()) in command
    assert command[-1] == "--quiet"
