# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Tests for the Tool and ToolAction helper behaviours."""

from __future__ import annotations

from pathlib import Path

from pyqa.config import Config
from pyqa.tools.base import DeferredCommand, Tool, ToolAction, ToolContext


def _make_tool() -> Tool:
    lint = ToolAction(name="lint", command=DeferredCommand(["echo", "lint"]))
    fix = ToolAction(name="fix", command=DeferredCommand(["echo", "fix"]), is_fix=True)
    return Tool(name="demo", actions=(lint, fix), languages=("python",))


def test_tool_iterable_and_indexable(tmp_path: Path) -> None:
    tool = _make_tool()

    assert len(tool) == 2
    actions = list(tool)
    assert [action.name for action in actions] == ["lint", "fix"]
    assert "lint" in tool
    assert actions[0] in tool

    assert tool[0].name == "lint"
    assert tool["fix"].is_fix is True
    assert list(tool.keys()) == ["lint", "fix"]
    assert [action.name for action in tool.values()] == ["lint", "fix"]
    assert [(name, action.name) for name, action in tool.items()] == [
        ("lint", "lint"),
        ("fix", "fix"),
    ]
    assert tool.get("lint").name == "lint"
    assert tool.get("missing") is None


def test_tool_context_builds_commands(tmp_path: Path) -> None:
    tool = _make_tool()
    cfg = Config()
    ctx = ToolContext(cfg=cfg, root=tmp_path, files=[tmp_path / "sample.py"])

    action = tool["lint"]
    command = action.build_command(ctx)
    assert command[-1].endswith("sample.py")
