# SPDX-License-Identifier: MIT

# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Tests for the sqlfluff strategy."""

from __future__ import annotations

from pathlib import Path

from pyqa.catalog import ToolCatalogLoader
from pyqa.catalog.strategies import command_option_map
from pyqa.config import Config
from pyqa.tools.base import ToolAction, ToolContext

_PYQA_ROOT = Path(__file__).resolve().parents[1]
_CATALOG_ROOT = _PYQA_ROOT / "tooling" / "catalog"


def _sqlfluff_config(action: str) -> dict[str, object]:
    loader = ToolCatalogLoader(catalog_root=_CATALOG_ROOT)
    snapshot = loader.load_snapshot()
    for definition in snapshot.tools:
        if definition.name == "sqlfluff":
            for candidate in definition.actions:
                if candidate.name == action:
                    return dict(candidate.command.reference.config)
    raise AssertionError(
        f"sqlfluff command configuration for action '{action}' missing from catalog",
    )


def test_sqlfluff_lint_command(tmp_path: Path) -> None:
    cfg = Config()
    cfg.execution.sql_dialect = "ansi"
    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[tmp_path / "queries" / "query.sql"],
        settings={
            "config": tmp_path / ".sqlfluff",
            "templater": "jinja",
            "rules": ["L001"],
            "args": ["queries"],
        },
    )

    builder = command_option_map(_sqlfluff_config("lint"))
    action = ToolAction(name="lint", command=builder, append_files=False)

    command = action.build_command(ctx)
    assert command[:2] == ["sqlfluff", "lint"]
    assert "--config" in command and str((tmp_path / ".sqlfluff").resolve()) in command
    assert "--templater" in command and "jinja" in command
    assert "--rules" in command and "L001" in command
    assert command[-1] == "queries"


def test_sqlfluff_fix_command(tmp_path: Path) -> None:
    ctx = ToolContext(
        cfg=Config(),
        root=tmp_path,
        files=[],
        settings={},
    )

    builder = command_option_map(_sqlfluff_config("fix"))
    action = ToolAction(name="fix", command=builder)

    command = action.build_command(ctx)
    assert command[:2] == ["sqlfluff", "fix"]
    assert "--force" in command
