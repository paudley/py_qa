# SPDX-License-Identifier: MIT
"""Behavioural tests for :mod:`pyqa.tools.registry`."""

from __future__ import annotations

from pathlib import Path

from pyqa.config import Config
from pyqa.tools.base import DeferredCommand, Tool, ToolAction, ToolContext
from pyqa.tools.registry import ToolRegistry


def _make_tool(name: str) -> Tool:
    action = ToolAction(name="lint", command=DeferredCommand(["echo", name]))
    return Tool(name=name, actions=(action,), languages=("python",))


def test_registry_behaves_like_mapping(tmp_path: Path) -> None:
    registry = ToolRegistry()
    tool = _make_tool("demo")
    registry.register(tool)

    assert len(registry) == 1
    assert "demo" in registry
    assert registry["demo"] is tool
    assert list(registry.keys()) == ["demo"]
    assert list(registry.values()) == [tool]
    assert list(registry.items()) == [("demo", tool)]
    assert list(iter(registry)) == ["demo"]


def test_registry_tools_for_language(tmp_path: Path) -> None:
    registry = ToolRegistry()
    py_tool = _make_tool("py-lint")
    js_tool = Tool(
        name="js-lint",
        actions=(ToolAction(name="lint", command=DeferredCommand(["echo", "js"])),),
        languages=("javascript",),
    )
    registry.register(py_tool)
    registry.register(js_tool)

    python_tools = list(registry.tools_for_language("python"))
    javascript_tools = list(registry.tools_for_language("javascript"))

    assert python_tools == [py_tool]
    assert javascript_tools == [js_tool]


def test_registry_tools_iterator_builds_commands(tmp_path: Path) -> None:
    registry = ToolRegistry()
    tool = _make_tool("demo")
    registry.register(tool)

    cfg = Config()
    ctx = ToolContext(cfg=cfg, root=tmp_path, files=[tmp_path / "file.py"])
    action = next(iter(tool.actions))

    command = action.build_command(ctx)
    assert command[-1].endswith("file.py")
