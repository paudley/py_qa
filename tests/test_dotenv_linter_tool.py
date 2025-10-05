# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Tests for dotenv-linter tool integration."""

from __future__ import annotations

from pathlib import Path

from pyqa.config import Config
from pyqa.catalog import ToolCatalogLoader
from pyqa.catalog.strategies import command_option_map
from pyqa.tools.base import ToolAction, ToolContext

_PYQA_ROOT = Path(__file__).resolve().parents[1]
_CATALOG_ROOT = _PYQA_ROOT / "tooling" / "catalog"


def _dotenv_linter_config() -> dict[str, object]:
    loader = ToolCatalogLoader(catalog_root=_CATALOG_ROOT)
    snapshot = loader.load_snapshot()
    for definition in snapshot.tools:
        if definition.name == "dotenv-linter":
            return dict(definition.actions[0].command.reference.config)
    raise AssertionError("dotenv-linter command configuration missing from catalog")


def test_dotenv_linter_command_build(tmp_path: Path) -> None:
    cfg = Config()
    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[tmp_path / "config" / ".env"],
        settings={
            "exclude": [tmp_path / "config" / ".env.local"],
            "skip": ["LowercaseKey"],
            "schema": tmp_path / "schema" / "env.json",
            "recursive": True,
            "args": ["--not-check-updates"],
        },
    )

    builder = command_option_map(_dotenv_linter_config())
    action = ToolAction(name="lint", command=builder)
    command = action.build_command(ctx)

    assert command[0] == "dotenv-linter"
    assert "--no-color" in command
    assert "--quiet" in command
    assert "--exclude" in command
    assert "--skip" in command
    assert "--schema" in command and str((tmp_path / "schema" / "env.json").resolve()) in command
    assert "--recursive" in command
    assert command[-1].endswith(".env")
