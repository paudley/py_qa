# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Smoke tests for lint CLI behaviors."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from textwrap import dedent
from typing import Any
from types import SimpleNamespace

import click
import pytest
from typer.main import get_group
from typer.testing import CliRunner

from pyqa.cli.app import app
from pyqa.cli.commands.lint import command as lint_module
from pyqa.cli.commands.lint import reporting as lint_reporting
from pyqa.cli.commands.lint import runtime as lint_runtime
from pyqa.cli.core.options import LintOptions
from pyqa.cli.core.typer_ext import _primary_option_name
from pyqa.config import Config
from pyqa.core.config.loader import ConfigLoader
from pyqa.core.environment.tool_env.models import PreparedCommand
from pyqa.core.models import Diagnostic, RunResult, ToolOutcome, ToolExitCategory
from pyqa.core.severity import Severity
from pyqa.linting.base import InternalLintReport
from pyqa.linting.registry import InternalLinterDefinition


def test_lint_warns_when_py_qa_path_outside_workspace(tmp_path: Path, monkeypatch) -> None:
    runner = CliRunner()

    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "py_qa").mkdir()

    monkeypatch.chdir(project_root)

    def fake_run_tool_info(tool_name, root, *, cfg=None, console=None, catalog_snapshot=None):
        assert tool_name == "ruff"
        return 0

    monkeypatch.setattr("pyqa.cli.commands.lint.meta.run_tool_info", fake_run_tool_info)

    result = runner.invoke(
        app,
        [
            "lint",
            "py_qa",
            "--root",
            str(project_root),
            "--tool-info",
            "ruff",
            "--no-emoji",
        ],
    )

    assert result.exit_code == 0
    assert "'py_qa' directories are skipped" in result.stdout


def test_lint_fetch_all_tools_flag(monkeypatch, tmp_path: Path) -> None:
    runner = CliRunner()

    prepared = PreparedCommand.from_parts(cmd=["demo"], env={}, version="1.2.3", source="local")
    calls: list[tuple] = []

    class FakeOrchestrator:
        def __init__(self, hooks):
            self._hooks = hooks

        def fetch_all_tools(self, cfg, root, callback=None):  # noqa: ANN001
            if callback:
                callback("start", "demo", "lint", 1, 1, None)
                callback("completed", "demo", "lint", 1, 1, None)
            calls.append((cfg, root))
            return [("demo", "lint", prepared, None)]

        def run(self, config, root):  # pragma: no cover - not used in this test
            raise AssertionError("unexpected orchestrator.run call")

    monkeypatch.setattr(
        lint_runtime,
        "DEFAULT_LINT_DEPENDENCIES",
        replace(
            lint_runtime.DEFAULT_LINT_DEPENDENCIES,
            orchestrator_factory=lambda registry, discovery, hooks: FakeOrchestrator(hooks),
        ),
    )
    monkeypatch.setattr("pyqa.cli.commands.lint.command.is_tty", lambda: False)

    result = runner.invoke(
        app,
        [
            "lint",
            "--fetch-all-tools",
            "--root",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0
    assert calls
    assert "Tool Preparation" in result.stdout
    assert "demo" in result.stdout
    assert "lint" in result.stdout
    assert "Phase" in result.stdout
    assert "ready" in result.stdout


def test_lint_validate_schema_flag(monkeypatch) -> None:
    runner = CliRunner()

    project_root = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(project_root)

    result = runner.invoke(
        app,
        [
            "lint",
            "--validate-schema",
            "--no-color",
            "--no-emoji",
        ],
    )

    assert result.exit_code == 0
    assert "Catalog validation succeeded" in result.stdout


def test_lint_validate_schema_conflicts(monkeypatch) -> None:
    runner = CliRunner()
    project_root = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(project_root)

    result = runner.invoke(
        app,
        [
            "lint",
            "--validate-schema",
            "--doctor",
        ],
    )

    assert result.exit_code != 0
    combined_output = (result.stdout or "") + (result.stderr or "")
    assert "cannot be combined" in combined_output


def test_docstring_linter_passes(tmp_path: Path, monkeypatch) -> None:
    from pyqa.analysis.treesitter.grammars import ensure_language

    if ensure_language("python") is None:
        pytest.skip("Python Tree-sitter grammar unavailable")

    package = tmp_path / "pkg"
    package.mkdir()
    module = package / "helpers.py"
    module.write_text(
        dedent(
            '''
            """Module docstring."""


            def add(first: int, second: int) -> int:
                """Add two integers.

                Args:
                    first: First operand.
                    second: Second operand.

                Returns:
                    int: Sum of the operands.
                """

                return first + second
            '''
        ),
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(app, ["lint", "--check-docstrings", "--root", str(tmp_path), "--no-emoji"])

    assert result.exit_code == 0
    assert "Docstring checks passed" in result.stdout


def test_docstring_linter_fails(tmp_path: Path, monkeypatch) -> None:
    from pyqa.analysis.treesitter.grammars import ensure_language

    if ensure_language("python") is None:
        pytest.skip("Python Tree-sitter grammar unavailable")

    package = tmp_path / "pkg"
    package.mkdir()
    module = package / "utils.py"
    module.write_text(
        dedent(
            '''
            """Module docstring missing function docs."""


            def helper(value: int) -> int:
                return value
            '''
        ),
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(app, ["lint", "--check-docstrings", "--root", str(tmp_path), "--no-emoji"])

    assert result.exit_code != 0
    combined = result.stdout + result.stderr
    assert "missing a docstring" in combined.lower()


def test_docstring_only_flag_surfaces_diagnostics(tmp_path: Path, monkeypatch) -> None:
    from pyqa.analysis.treesitter.grammars import ensure_language

    if ensure_language("python") is None:
        pytest.skip("Python Tree-sitter grammar unavailable")

    module = tmp_path / "cli.py"
    module.write_text(
        """
def command() -> None:
    pass
""".strip()
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "lint",
            "--only",
            "docstrings",
            "--root",
            str(tmp_path),
            "--no-emoji",
        ],
    )

    assert result.exit_code != 0
    combined = (result.stdout + result.stderr).lower()
    assert "missing a docstring" in combined


def test_lint_no_stats_flag(monkeypatch, tmp_path: Path) -> None:
    runner = CliRunner()
    captured: dict[str, Any] = {}

    original_build_config = lint_module.build_config

    def fake_build_config(options):
        captured["options"] = options
        return original_build_config(options)

    monkeypatch.setattr(lint_module, "build_config", fake_build_config)

    def _run(config, root):
        captured["config"] = config
        return RunResult(root=root, files=[], outcomes=[], tool_versions={})

    class FakeOrchestrator:
        def __init__(self, hooks):
            self._hooks = hooks

        def run(self, config, root):
            return _run(config, root)

        def fetch_all_tools(self, config, root, callback=None):  # pragma: no cover - unused
            return []

    monkeypatch.setattr(
        lint_runtime,
        "DEFAULT_LINT_DEPENDENCIES",
        replace(
            lint_runtime.DEFAULT_LINT_DEPENDENCIES,
            orchestrator_factory=lambda registry, discovery, hooks: FakeOrchestrator(hooks),
        ),
    )

    result = runner.invoke(
        app,
        [
            "lint",
            "--root",
            str(tmp_path),
            "--no-color",
            "--no-emoji",
            "--no-stats",
        ],
    )


def test_lint_no_lint_tests_flag(monkeypatch, tmp_path: Path) -> None:
    runner = CliRunner()
    captured: dict[str, Any] = {}

    original_build_config = lint_module.build_config

    def fake_build_config(options):
        captured["options"] = options
        return original_build_config(options)

    def _run(config, root):
        captured["config"] = config
        return RunResult(root=root, files=[], outcomes=[], tool_versions={})

    tests_dir = tmp_path / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(lint_module, "build_config", fake_build_config)

    class FakeRunOrchestrator:
        def __init__(self, hooks):
            self._hooks = hooks

        def run(self, config, root):
            return _run(config, root)

        def fetch_all_tools(self, config, root, callback=None):  # pragma: no cover - unused
            return []

    monkeypatch.setattr(
        lint_runtime,
        "DEFAULT_LINT_DEPENDENCIES",
        replace(
            lint_runtime.DEFAULT_LINT_DEPENDENCIES,
            orchestrator_factory=lambda registry, discovery, hooks: FakeRunOrchestrator(hooks),
        ),
    )

    result = runner.invoke(
        app,
        [
            "lint",
            "--root",
            str(tmp_path),
            "--no-lint-tests",
            "--no-color",
            "--no-emoji",
        ],
    )

    assert result.exit_code == 0
    options = captured["options"]
    assert isinstance(options, LintOptions)
    assert Path("tests") in options.exclude
    config = captured["config"]
    assert isinstance(config, Config)
    resolved_tests = (tmp_path / "tests").resolve()
    assert any(path == resolved_tests for path in config.file_discovery.excludes)


def test_append_quality_checks_adds_outcome(tmp_path: Path) -> None:
    target = tmp_path / "module.py"
    target.write_text("print('hello')\n", encoding="utf-8")

    config_path = tmp_path / "pyproject.toml"
    config_path.write_text(
        """
[tool.pyqa.quality]
checks = ["license"]

[tool.pyqa.license]
spdx = "MIT"
year = "2025"
copyright = "Blackcat"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    loader = ConfigLoader.for_root(tmp_path)
    load_result = loader.load_with_trace()
    config = load_result.config
    config.severity.sensitivity = "maximum"

    run_result = RunResult(
        root=tmp_path,
        files=[target],
        outcomes=[],
        tool_versions={},
    )

    class _StubLogger:
        """Minimal CLI logger stub used for quality check tests."""

        def ok(self, message: str) -> None:
            pass

        def warn(self, message: str) -> None:
            pass

        def fail(self, message: str) -> None:
            pass

    stub_state = SimpleNamespace(
        root=tmp_path,
        options=SimpleNamespace(selection_options=SimpleNamespace(only=[], filters=[])),
        meta=_meta_flags(check_docstrings=False),
        logger=_StubLogger(),
    )

    lint_module._append_internal_quality_checks(
        config=config,
        state=stub_state,
        run_result=run_result,
    )

    quality_outcomes = [outcome for outcome in run_result.outcomes if outcome.tool == "quality"]
    assert quality_outcomes
    assert any("license" in outcome.action for outcome in quality_outcomes)
    assert any(
        "SPDX" in line or "license" in line.lower() or "copyright" in line.lower()
        for outcome in quality_outcomes
        for line in outcome.stdout
    )


def _build_stub_state(
    *,
    root: Path,
    only: list[str],
    filters: list[str],
    check_docstrings: bool,
    logger,
):
    return SimpleNamespace(
        root=root,
        options=SimpleNamespace(selection_options=SimpleNamespace(only=only, filters=filters)),
        meta=_meta_flags(check_docstrings=check_docstrings),
        logger=logger,
    )


def _make_docstring_report(path: Path, *, warnings: list[str] | None = None) -> InternalLintReport:
    diagnostics = [
        Diagnostic(
            file=str(path),
            line=1,
            column=None,
            severity=Severity.ERROR,
            message="Missing module docstring",
            tool="docstrings",
            code="docstrings:missing-module-docstring",
        ),
    ]
    outcome = ToolOutcome(
        tool="docstrings",
        action="check",
        returncode=1,
        stdout=[f"{path}:1: Missing module docstring"],
        stderr=warnings or [],
        diagnostics=diagnostics,
        exit_category=ToolExitCategory.DIAGNOSTIC,
    )
    return InternalLintReport(outcome=outcome, files=(path,))


class _CapturingLogger:
    def __init__(self) -> None:
        self.ok_messages: list[str] = []
        self.warn_messages: list[str] = []
        self.fail_messages: list[str] = []

    def ok(self, message: str) -> None:
        self.ok_messages.append(message)

    def warn(self, message: str) -> None:
        self.warn_messages.append(message)

    def fail(self, message: str) -> None:
        self.fail_messages.append(message)


def _meta_flags(**overrides) -> SimpleNamespace:
    defaults = {
        "doctor": False,
        "tool_info": None,
        "fetch_all_tools": False,
        "validate_schema": False,
        "normal": False,
        "check_docstrings": False,
        "check_suppressions": False,
        "check_types_strict": False,
        "check_closures": False,
        "check_signatures": False,
        "check_cache_usage": False,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_append_quality_docstrings_meta(monkeypatch, tmp_path: Path) -> None:
    doc_path = tmp_path / "pkg" / "module.py"
    report = _make_docstring_report(doc_path, warnings=["spaCy missing"])
    captures: dict[str, Any] = {}

    def fake_run(state, *, emit_to_logger: bool):
        captures["emit_to_logger"] = emit_to_logger
        return report

    definition = InternalLinterDefinition(
        name="docstrings",
        meta_attribute="check_docstrings",
        selection_tokens=("docstring", "docstrings"),
        runner=fake_run,
        description="stub",
    )

    monkeypatch.setattr(lint_reporting, "iter_internal_linters", lambda: (definition,))

    logger = _CapturingLogger()
    state = _build_stub_state(
        root=tmp_path,
        only=[],
        filters=[],
        check_docstrings=True,
        logger=logger,
    )
    config = SimpleNamespace(
        quality=SimpleNamespace(enforce_in_lint=False),
        severity=SimpleNamespace(sensitivity="standard"),
        license=SimpleNamespace(),
    )
    run_result = RunResult(root=tmp_path, files=[], outcomes=[], tool_versions={})

    lint_module._append_internal_quality_checks(
        config=config,
        state=state,
        run_result=run_result,
        logger=state.logger,
    )

    assert captures["emit_to_logger"] is True
    assert run_result.outcomes[-1] is report.outcome
    assert doc_path in run_result.files
    assert not logger.warn_messages


def test_append_quality_docstrings_filters(monkeypatch, tmp_path: Path) -> None:
    doc_path = tmp_path / "pkg" / "module.py"
    report = _make_docstring_report(doc_path, warnings=["spaCy missing"])
    captures: dict[str, Any] = {}

    def fake_run(state, *, emit_to_logger: bool):
        captures["emit_to_logger"] = emit_to_logger
        return report

    definition = InternalLinterDefinition(
        name="docstrings",
        meta_attribute="check_docstrings",
        selection_tokens=("docstring", "docstrings"),
        runner=fake_run,
        description="stub",
    )

    monkeypatch.setattr(lint_reporting, "iter_internal_linters", lambda: (definition,))

    logger = _CapturingLogger()
    state = _build_stub_state(
        root=tmp_path,
        only=["docstrings"],
        filters=[],
        check_docstrings=False,
        logger=logger,
    )
    config = SimpleNamespace(
        quality=SimpleNamespace(enforce_in_lint=False),
        severity=SimpleNamespace(sensitivity="standard"),
        license=SimpleNamespace(),
    )
    run_result = RunResult(root=tmp_path, files=[], outcomes=[], tool_versions={})

    lint_module._append_internal_quality_checks(
        config=config,
        state=state,
        run_result=run_result,
        logger=state.logger,
    )

    assert captures["emit_to_logger"] is False
    assert run_result.outcomes[-1] is report.outcome
    assert doc_path in run_result.files
    assert logger.warn_messages == report.outcome.stderr


def test_append_internal_linter_meta_flag(monkeypatch, tmp_path: Path) -> None:
    captures: dict[str, Any] = {}

    def fake_runner(state, *, emit_to_logger: bool) -> InternalLintReport:
        captures["emit"] = emit_to_logger
        outcome = ToolOutcome(
            tool="internal-suppressions",
            action="check",
            returncode=0,
            stdout=[],
            stderr=[],
            diagnostics=[],
            exit_category=ToolExitCategory.SUCCESS,
        )
        return InternalLintReport(outcome=outcome, files=())

    definition = InternalLinterDefinition(
        name="suppressions",
        meta_attribute="check_suppressions",
        selection_tokens=("suppressions",),
        runner=fake_runner,
        description="stub",
    )

    monkeypatch.setattr(lint_reporting, "iter_internal_linters", lambda: (definition,))

    state = SimpleNamespace(
        root=tmp_path,
        options=SimpleNamespace(selection_options=SimpleNamespace(only=[], filters=[])),
        meta=_meta_flags(check_suppressions=True),
        logger=_CapturingLogger(),
    )
    config = SimpleNamespace(
        quality=SimpleNamespace(enforce_in_lint=False),
        severity=SimpleNamespace(sensitivity="standard"),
        license=SimpleNamespace(),
    )
    run_result = RunResult(root=tmp_path, files=[], outcomes=[], tool_versions={})

    lint_module._append_internal_quality_checks(
        config=config,
        state=state,
        run_result=run_result,
        logger=state.logger,
    )

    assert captures["emit"] is True
    assert any(outcome.tool == "internal-suppressions" for outcome in run_result.outcomes)


def test_append_internal_linter_selection(monkeypatch, tmp_path: Path) -> None:
    captures: dict[str, Any] = {}

    def fake_runner(state, *, emit_to_logger: bool) -> InternalLintReport:
        captures.setdefault("invocations", 0)
        captures["invocations"] += 1
        outcome = ToolOutcome(
            tool="internal-cache",
            action="check",
            returncode=0,
            stdout=["warning"],
            stderr=["warning"],
            diagnostics=[],
            exit_category=ToolExitCategory.SUCCESS,
        )
        return InternalLintReport(outcome=outcome, files=())

    definition = InternalLinterDefinition(
        name="cache",
        meta_attribute="check_cache_usage",
        selection_tokens=("cache",),
        runner=fake_runner,
        description="stub",
    )

    monkeypatch.setattr(lint_reporting, "iter_internal_linters", lambda: (definition,))

    capturing_logger = _CapturingLogger()
    state = SimpleNamespace(
        root=tmp_path,
        options=SimpleNamespace(selection_options=SimpleNamespace(only=["cache"], filters=[])),
        meta=_meta_flags(),
        logger=capturing_logger,
    )
    config = SimpleNamespace(
        quality=SimpleNamespace(enforce_in_lint=False),
        severity=SimpleNamespace(sensitivity="standard"),
        license=SimpleNamespace(),
    )
    run_result = RunResult(root=tmp_path, files=[], outcomes=[], tool_versions={})

    lint_module._append_internal_quality_checks(
        config=config,
        state=state,
        run_result=run_result,
        logger=capturing_logger,
    )

    assert captures.get("invocations", 0) == 1
    assert capturing_logger.warn_messages == ["warning"]
    assert any(outcome.tool == "internal-cache" for outcome in run_result.outcomes)


def test_lint_meta_normal_applies_defaults(monkeypatch, tmp_path: Path) -> None:
    runner = CliRunner()
    captured: dict[str, Any] = {}

    original_build_config = lint_module.build_config

    def fake_build_config(options):
        captured["options"] = options
        return original_build_config(options)

    tests_dir = tmp_path / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(lint_module, "build_config", fake_build_config)

    def _run(config, root):
        captured["config"] = config
        return RunResult(root=root, files=[], outcomes=[], tool_versions={})

    class FakeOrchestrator:
        def __init__(self, hooks):
            self._hooks = hooks

        def run(self, config, root):
            return _run(config, root)

        def fetch_all_tools(self, config, root, callback=None):  # pragma: no cover - unused
            return []

    monkeypatch.setattr(
        lint_runtime,
        "DEFAULT_LINT_DEPENDENCIES",
        replace(
            lint_runtime.DEFAULT_LINT_DEPENDENCIES,
            orchestrator_factory=lambda registry, discovery, hooks: FakeOrchestrator(hooks),
        ),
    )

    result = runner.invoke(
        app,
        [
            "lint",
            "--root",
            str(tmp_path),
            "-n",
            "normal",
            "--no-color",
            "--no-emoji",
        ],
    )

    assert result.exit_code == 0
    options = captured["options"]
    assert isinstance(options, LintOptions)
    assert options.advice is True
    assert options.use_local_linters is True
    assert options.no_lint_tests is True
    assert options.output_mode == "concise"
    assert Path("tests") in options.exclude
    config = captured["config"]
    assert isinstance(config, Config)
    resolved_tests = (tmp_path / "tests").resolve()
    assert any(path == resolved_tests for path in config.file_discovery.excludes)


def test_concise_mode_renders_progress_status(monkeypatch, tmp_path: Path) -> None:
    runner = CliRunner()

    progress_instances: list[_FakeProgress] = []

    class _FakeProgress:
        def __init__(self, *args, **kwargs) -> None:
            progress_instances.append(self)
            self.records: list[tuple] = []
            self._tasks: dict[int, dict[str, object]] = {}
            self._next_id = 1
            self._started = False

        def start(self) -> None:
            if not self._started:
                self.records.append(("start",))
                self._started = True

        def stop(self) -> None:
            if self._started:
                self.records.append(("stop",))
                self._started = False

        def add_task(self, description: str, *, total: int = 0, **fields: object) -> int:
            task_id = self._next_id
            self._next_id += 1
            self._tasks[task_id] = {
                "description": description,
                "total": total,
                "completed": 0,
                "fields": dict(fields),
            }
            self.records.append(("add", description, total, dict(fields)))
            return task_id

        def update(
            self,
            task_id: int,
            *,
            description: str | None = None,
            total: int | None = None,
            **fields: object,
        ) -> None:
            task = self._tasks[task_id]
            if description is not None:
                task["description"] = description
            if total is not None:
                task["total"] = total
            if fields:
                task_fields = task["fields"]
                assert isinstance(task_fields, dict)
                task_fields.update(fields)
            snapshot_fields = dict(task["fields"])
            self.records.append(("update", task["description"], task["total"], snapshot_fields))

        def advance(self, task_id: int, advance: int = 1) -> None:
            task = self._tasks[task_id]
            task["completed"] = int(task["completed"]) + advance
            self.records.append(("advance", task["completed"]))

        def get_task(self, task_id: int):
            task = self._tasks[task_id]
            from types import SimpleNamespace

            return SimpleNamespace(
                total=task["total"],
                completed=task["completed"],
            )

    monkeypatch.setattr(lint_module, "Progress", _FakeProgress)
    monkeypatch.setattr(lint_module, "is_tty", lambda: True)

    orchestrator_state: dict[str, _HookingOrchestrator | None] = {"instance": None}

    def _run(config, root):
        orchestrator = orchestrator_state["instance"]
        assert orchestrator is not None
        hooks = orchestrator._hooks
        if hooks.after_discovery:
            hooks.after_discovery(1)
        if hooks.before_tool:
            hooks.before_tool("ruff")
        outcome_check = ToolOutcome(
            tool="ruff",
            action="lint",
            returncode=0,
            stdout="",
            stderr="",
            diagnostics=[],
        )
        outcome_fix = ToolOutcome(
            tool="ruff",
            action="fix",
            returncode=0,
            stdout="",
            stderr="",
            diagnostics=[],
        )
        if hooks.after_tool:
            hooks.after_tool(outcome_check)
            hooks.after_tool(outcome_fix)
        result = RunResult(
            root=root,
            files=[],
            outcomes=[outcome_check, outcome_fix],
            tool_versions={},
        )
        if hooks.after_execution:
            hooks.after_execution(result)
        return result

    class _HookingOrchestrator:
        def __init__(self, hooks):
            self._hooks = hooks

        def run(self, config, root):
            return _run(config, root)

        def fetch_all_tools(self, config, root, callback=None):  # pragma: no cover - unused
            return []

    def _factory(registry, discovery, hooks):
        orchestrator_state["instance"] = _HookingOrchestrator(hooks)
        return orchestrator_state["instance"]

    monkeypatch.setattr(
        lint_runtime,
        "DEFAULT_LINT_DEPENDENCIES",
        replace(
            lint_runtime.DEFAULT_LINT_DEPENDENCIES,
            orchestrator_factory=_factory,
        ),
    )

    result = runner.invoke(
        app,
        [
            "lint",
            "--root",
            str(tmp_path),
            "--no-emoji",
        ],
    )

    assert result.exit_code == 0
    assert progress_instances, "progress bar should initialise"
    records = progress_instances[0].records
    assert any(event[0] == "start" for event in records)
    advances = [event for event in records if event[0] == "advance"]
    assert len(advances) == 4, "two actions plus post-processing and rendering phases should advance"
    assert any(event[0] == "update" and event[2] == 4 for event in records), (
        "progress total should include tool actions and extra phases"
    )
    assert any(event[0] == "update" and event[1].startswith("Linting ruff") for event in records)
    status_updates = [event for event in records if event[0] == "update" and isinstance(event[3], dict)]
    status_values = [event[3].get("current_status", "") for event in status_updates]
    assert any("queued" in status for status in status_values)
    assert any("post-processing" in status for status in status_values)
    assert any("rendering output" in status for status in status_values)
    assert any("done" in status for status in status_values), "progress should report completion"
    assert any(event[0] == "stop" for event in records), "progress should stop after completion"


def test_lint_help_options_sorted() -> None:
    lint_cmd = get_group(app).commands["lint"]
    ctx = click.Context(lint_cmd)
    formatter = _RecordingFormatter()
    lint_cmd.format_options(ctx, formatter)  # type: ignore[arg-type]

    options_section = formatter.sections.get("Options")
    assert options_section is not None

    expected = _expected_sorted_options(lint_cmd, ctx)
    assert options_section == expected


class _RecordingFormatter:
    def __init__(self) -> None:
        self.sections: dict[str, list[tuple[str, str]]] = {}
        self._current: str | None = None

    @contextmanager
    def section(self, title: str):
        previous = self._current
        self._current = title
        try:
            yield
        finally:
            self._current = previous

    def write_dl(self, rows: list[tuple[str, str]]) -> None:
        if self._current is None:
            return
        self.sections.setdefault(self._current, []).extend(rows)


def _expected_sorted_options(command, ctx: click.Context) -> list[tuple[str, str]]:
    option_records: list[tuple[tuple[str, int], tuple[str, str]]] = []
    for index, param in enumerate(command.get_params(ctx)):
        if getattr(param, "param_type_name", "") == "argument":
            continue
        record = param.get_help_record(ctx)
        if record is None:
            continue
        option_records.append(((_primary_option_name(param), index), record))
    return [record for _, record in sorted(option_records, key=lambda entry: entry[0])]
