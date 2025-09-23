# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Integration tests for orchestrator execution flow."""

# pylint: disable=missing-function-docstring

import subprocess
from pathlib import Path

from pyqa.config import Config
from pyqa.execution.orchestrator import Orchestrator
from pyqa.tools.base import Tool, ToolAction, ToolContext
from pyqa.tools.registry import ToolRegistry


class FakeDiscovery:
    """Simple stub returning a pre-defined file list."""

    # pylint: disable=too-few-public-methods
    def __init__(self, files: list[Path]) -> None:
        self._files = files

    def run(self, *_args, **_kwargs) -> list[Path]:
        return self._files


class SettingsCommand:
    """Command builder used in tests to verify settings propagation."""

    def build(self, ctx: ToolContext) -> list[str]:
        cmd = ["dummy"]
        args = ctx.settings.get("args")
        if args is None:
            args_list: list[str] = []
        elif isinstance(args, (list, tuple, set)):
            args_list = [str(arg) for arg in args]
        else:
            args_list = [str(args)]
        cmd.extend(args_list)
        return cmd


def test_orchestrator_runs_registered_tool(tmp_path: Path) -> None:
    target = tmp_path / "module.py"
    target.write_text("print('ok')\n", encoding="utf-8")

    registry = ToolRegistry()

    registry.register(
        Tool(
            name="dummy",
            actions=(
                ToolAction(
                    name="lint",
                    command=SettingsCommand(),
                ),
            ),
            file_extensions=(".py",),
            runtime="binary",
        )
    )

    def runner(cmd, **kwargs):
        assert cmd[0] == "dummy"
        assert cmd[1] == "--flag"
        assert Path(cmd[2]) == target
        env = kwargs.get("env", {})
        assert env.get("DUMMY_ENV") == "1"
        return subprocess.CompletedProcess(cmd, returncode=0, stdout="output", stderr="")

    orchestrator = Orchestrator(
        registry=registry,
        discovery=FakeDiscovery([target]),
        runner=runner,
    )

    cfg = Config()
    cfg.tool_settings["dummy"] = {
        "args": ["--flag"],
        "env": {"DUMMY_ENV": "1"},
    }

    result = orchestrator.run(cfg, root=tmp_path)

    assert len(result.outcomes) == 1
    outcome = result.outcomes[0]
    assert outcome.tool == "dummy"
    assert outcome.returncode == 0
    assert outcome.stdout == "output"
    assert not outcome.stderr


def test_orchestrator_uses_cache(tmp_path: Path) -> None:
    target = tmp_path / "module.py"
    target.write_text("print('ok')\n", encoding="utf-8")

    registry = ToolRegistry()
    registry.register(
        Tool(
            name="dummy",
            actions=(
                ToolAction(
                    name="lint",
                    command=SettingsCommand(),
                ),
            ),
            file_extensions=(".py",),
            runtime="binary",
        )
    )

    cfg = Config()
    cfg.execution.cache_enabled = True
    cfg.execution.cache_dir = tmp_path / ".cache"
    cfg.execution.jobs = 1

    calls: list[list[str]] = []

    def runner(cmd, **kwargs):
        calls.append(list(cmd))
        return subprocess.CompletedProcess(cmd, returncode=0, stdout="output", stderr="")

    orchestrator = Orchestrator(
        registry=registry,
        discovery=FakeDiscovery([target]),
        runner=runner,
    )
    orchestrator.run(cfg, root=tmp_path)
    assert len(calls) == 1

    def runner_fail(cmd, **_kwargs):
        raise AssertionError(f"cache miss for {cmd}")

    orchestrator_cached = Orchestrator(
        registry=registry,
        discovery=FakeDiscovery([target]),
        runner=runner_fail,
    )
    result = orchestrator_cached.run(cfg, root=tmp_path)

    assert len(result.outcomes) == 1
    assert result.outcomes[0].stdout == "output"

    cfg.tool_settings["dummy"] = {"args": ["--different"]}
    calls_after: list[list[str]] = []

    def runner_settings(cmd, **kwargs):
        calls_after.append(list(cmd))
        return subprocess.CompletedProcess(cmd, returncode=0, stdout="updated", stderr="")

    orchestrator_settings = Orchestrator(
        registry=registry,
        discovery=FakeDiscovery([target]),
        runner=runner_settings,
    )
    result_settings = orchestrator_settings.run(cfg, root=tmp_path)
    assert len(calls_after) == 1
    assert result_settings.outcomes[0].stdout == "updated"
