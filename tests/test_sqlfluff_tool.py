# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Tests for sqlfluff command builder."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

from pyqa.tools.base import ToolContext
from pyqa.tools.builtins import SqlfluffCommand


def _context(root: Path, *, settings: dict[str, object] | None = None) -> ToolContext:
    cfg = Mock()
    cfg.execution.line_length = 120
    cfg.execution.sql_dialect = "postgresql"
    return ToolContext(cfg=cfg, root=root, files=[], settings=settings or {})


def test_sqlfluff_command_uses_global_dialect(tmp_path: Path) -> None:
    ctx = _context(tmp_path)
    cmd = SqlfluffCommand(base=("sqlfluff", "lint", "--format", "json")).build(ctx)
    assert "--dialect" in cmd
    assert "postgresql" in cmd


def test_sqlfluff_command_respects_override(tmp_path: Path) -> None:
    ctx = _context(tmp_path, settings={"dialect": "mysql"})
    cmd = SqlfluffCommand(base=("sqlfluff", "lint", "--format", "json")).build(ctx)
    index = cmd.index("--dialect")
    assert cmd[index + 1] == "mysql"
