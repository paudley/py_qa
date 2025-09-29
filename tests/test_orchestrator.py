# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Integration tests for orchestrator execution flow."""

import subprocess
from collections.abc import Sequence
from pathlib import Path

from pyqa.config import Config
from pyqa.execution.orchestrator import Orchestrator
from pyqa.models import RawDiagnostic
from pyqa.testing import flatten_test_suppressions
from pyqa.tool_env.models import PreparedCommand
from pyqa.tools.base import DeferredCommand, Tool, ToolAction, ToolContext
from pyqa.tools.registry import ToolRegistry


class FakeDiscovery:
    """Simple stub returning a pre-defined file list."""

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


class StubPreparer:
    """Stub command preparer capturing tool/action ordering."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def prepare(
        self,
        *,
        tool: Tool,
        base_cmd: Sequence[str],
        root: Path,
        cache_dir: Path,
        system_preferred: bool,
        use_local_override: bool,
    ) -> PreparedCommand:
        self.calls.append(tool.name)
        return PreparedCommand.from_parts(
            cmd=base_cmd,
            env={},
            version="1",
            source="system",
        )


def test_orchestrator_runs_registered_tool(tmp_path: Path) -> None:
    target = tmp_path / "module.py"
    target.write_text(
        "# SPDX-License-Identifier: MIT\nprint('ok')\n",
        encoding="utf-8",
    )

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
        ),
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
        ),
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


def test_orchestrator_filters_suppressed_diagnostics(tmp_path: Path) -> None:
    target = tmp_path / "tests" / "test_tool_env.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("print('ok')\n", encoding="utf-8")

    class StaticParser:
        def __init__(self, *diagnostics: RawDiagnostic) -> None:
            self._diagnostics = list(diagnostics)

        def parse(
            self,
            stdout: str,
            stderr: str,
            *,
            context: ToolContext,
        ) -> Sequence[RawDiagnostic]:
            del stdout, stderr, context
            return list(self._diagnostics)

    suppressed = RawDiagnostic(
        file="tests/test_tool_env.py",
        line=94,
        column=None,
        severity="warning",
        message="W0613 Unused argument 'command'",
        code="W0613",
        tool="pylint",
    )

    duplicate_comment = RawDiagnostic(
        file="tests/test_tool_env.py",
        line=1,
        column=None,
        severity="refactor",
        message=(
            "Similar lines in 2 files\n"
            "==tests/test_tool_env.py:[1:3]\n"
            "==tests/other.py:[5:7]\n"
            "    # SPDX-License-Identifier: MIT"
        ),
        code="R0801",
        tool="pylint",
    )

    registry = ToolRegistry()
    registry.register(
        Tool(
            name="pylint",
            actions=(
                ToolAction(
                    name="lint",
                    command=DeferredCommand(("pylint",)),
                    append_files=False,
                    parser=StaticParser(suppressed, duplicate_comment),
                ),
            ),
            file_extensions=(".py",),
            runtime="binary",
        ),
    )

    def runner(cmd, **_kwargs):
        return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

    orchestrator = Orchestrator(
        registry=registry,
        discovery=FakeDiscovery([target]),
        runner=runner,
    )

    cfg = Config()
    cfg.output.tool_filters["pylint"] = flatten_test_suppressions(("python",))["pylint"]

    result = orchestrator.run(cfg, root=tmp_path)

    assert len(result.outcomes) == 1
    outcome = result.outcomes[0]
    assert outcome.stdout == ""
    assert outcome.diagnostics == []


def test_fetch_all_tools_respects_phase_order(tmp_path: Path) -> None:
    registry = ToolRegistry()

    format_tool = Tool(
        name="format-tool",
        phase="format",
        actions=(
            ToolAction(
                name="format",
                command=DeferredCommand(("fmt",)),
            ),
        ),
        runtime="binary",
    )
    lint_tool = Tool(
        name="lint-tool",
        phase="lint",
        actions=(
            ToolAction(
                name="lint",
                command=DeferredCommand(("lint",)),
            ),
        ),
        runtime="binary",
    )
    format_b = Tool(
        name="format-b",
        phase="format",
        before=("format-tool",),
        actions=(
            ToolAction(
                name="format",
                command=DeferredCommand(("fmt-b",)),
            ),
        ),
        runtime="binary",
    )
    analysis_tool = Tool(
        name="analysis-tool",
        phase="analysis",
        after=("format-tool",),
        actions=(
            ToolAction(
                name="analyze",
                command=DeferredCommand(("analyze",)),
            ),
        ),
        runtime="binary",
    )

    registry.register(format_tool)
    registry.register(lint_tool)
    registry.register(format_b)
    registry.register(analysis_tool)

    preparer = StubPreparer()
    orchestrator = Orchestrator(
        registry=registry,
        discovery=FakeDiscovery([]),
        cmd_preparer=preparer,
    )

    cfg = Config()
    cfg.execution.only = [
        "format-tool",
        "analysis-tool",
        "lint-tool",
        "format-b",
    ]

    orchestrator.fetch_all_tools(cfg, root=tmp_path)

    assert preparer.calls == [
        "format-b",
        "format-tool",
        "lint-tool",
        "analysis-tool",
    ]


def test_installers_run_once(tmp_path: Path) -> None:
    calls: list[Path] = []

    def installer(context: ToolContext) -> None:
        calls.append(context.root)

    registry = ToolRegistry()
    registry.register(
        Tool(
            name="demo",
            actions=(
                ToolAction(
                    name="lint",
                    command=DeferredCommand(("demo",)),
                ),
            ),
            runtime="binary",
            installers=(installer,),
        ),
    )

    orchestrator = Orchestrator(
        registry=registry,
        discovery=FakeDiscovery([]),
    )

    cfg = Config()
    orchestrator.fetch_all_tools(cfg, root=tmp_path)
    assert len(calls) == 1

    def runner(cmd, **_kwargs):
        return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

    orchestrator_runtime = Orchestrator(
        registry=registry,
        discovery=FakeDiscovery([]),
        runner=runner,
    )
    orchestrator_runtime.run(cfg, root=tmp_path)
    assert len(calls) == 2
