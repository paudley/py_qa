# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Smoke tests for lint CLI behaviors."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from io import StringIO
from pathlib import Path
from textwrap import dedent
from typing import Any
from types import SimpleNamespace

import click
import pytest
from rich.console import Console
from typer.main import get_group
from typer.testing import CliRunner

from pyqa.cli.app import app
from pyqa.cli.commands.lint import command as lint_module
from pyqa.cli.commands.lint import runtime as lint_runtime
from pyqa.cli.core.options import LintOptions
from pyqa.cli.core.typer_ext import _primary_option_name
from pyqa.cli.commands.lint.params import (
    LintMetaParams,
    MetaActionParams,
    MetaAnalysisChecks,
    MetaRuntimeChecks,
    RuntimeAdditionalFlagOverrides,
    RuntimeCoreFlagOverrides,
    RuntimeFlagOverrides,
    RuntimeInterfaceFlagOverrides,
    RuntimePolicyFlagOverrides,
)
from pyqa.cli.commands.lint.preparation import PROVIDED_FLAG_INTERNAL_LINTERS
from pyqa.config import Config
from pyqa.core.config.loader import ConfigLoader
from pyqa.core.environment.tool_env.models import PreparedCommand
from pyqa.core.models import RunResult, ToolOutcome
from pyqa.core.severity import Severity
from pyqa.linting.interfaces import run_pyqa_interface_linter
from pyqa.linting.quality import (
    run_file_size_linter,
    run_license_header_linter,
    run_python_hygiene_linter,
)
from pyqa.linting.suppressions import SuppressionRegistry, run_suppression_linter
from pyqa.linting.registry import ensure_internal_tools_registered
from pyqa.orchestration.tool_selection import SelectionResult, ToolDecision, ToolEligibility
from pyqa.tools.base import ToolContext
from pyqa.tools.registry import ToolRegistry


def _meta_flags(
    *,
    normal: bool = False,
    explain_tools: bool = False,
    check_docstrings: bool = False,
    check_suppressions: bool = False,
    check_types_strict: bool = False,
    check_missing: bool = False,
    check_closures: bool = False,
    check_conditional_imports: bool = False,
    check_signatures: bool = False,
    check_cache_usage: bool = False,
    check_value_types: bool = False,
    check_value_types_general: bool = False,
    check_interfaces: bool = False,
    check_di: bool = False,
    check_module_docs: bool = False,
    check_pyqa_python_hygiene: bool = False,
    show_valid_suppressions: bool = False,
    check_license_header: bool = False,
    check_copyright: bool = False,
    check_python_hygiene: bool = False,
    check_file_size: bool = False,
    check_schema_sync: bool = False,
    pyqa_rules: bool = False,
) -> LintMetaParams:
    """Return ``LintMetaParams`` populated for test scenarios."""

    return LintMetaParams(
        actions=MetaActionParams(
            doctor=False,
            tool_info=None,
            fetch_all_tools=False,
            validate_schema=False,
            normal=normal,
            explain_tools=explain_tools,
        ),
        analysis=MetaAnalysisChecks(
            check_docstrings=check_docstrings,
            check_suppressions=check_suppressions,
            check_types_strict=check_types_strict,
            check_missing=check_missing,
        ),
        runtime=MetaRuntimeChecks(
            flags=RuntimeFlagOverrides(
                core=RuntimeCoreFlagOverrides(
                    check_closures=check_closures,
                    check_conditional_imports=check_conditional_imports,
                    check_signatures=check_signatures,
                    check_cache_usage=check_cache_usage,
                    check_value_types=check_value_types,
                    check_value_types_general=check_value_types_general,
                ),
                interface=RuntimeInterfaceFlagOverrides(
                    check_interfaces=check_interfaces,
                    check_di=check_di,
                    check_module_docs=check_module_docs,
                    check_pyqa_python_hygiene=check_pyqa_python_hygiene,
                ),
                policy=RuntimePolicyFlagOverrides(
                    show_valid_suppressions=show_valid_suppressions,
                    check_license_header=check_license_header,
                    check_copyright=check_copyright,
                    check_python_hygiene=check_python_hygiene,
                ),
                additional=RuntimeAdditionalFlagOverrides(
                    check_file_size=check_file_size,
                    check_schema_sync=check_schema_sync,
                    pyqa_rules=pyqa_rules,
                ),
            ),
        ),
    )


class _CapturingLogger:
    """Stub CLI logger that records messages for assertions."""

    def __init__(self) -> None:
        self.ok_messages: list[str] = []
        self.warn_messages: list[str] = []
        self.fail_messages: list[str] = []
        self.echo_messages: list[str] = []

    def ok(self, message: str) -> None:
        self.ok_messages.append(message)

    def warn(self, message: str) -> None:
        self.warn_messages.append(message)

    def fail(self, message: str) -> None:
        self.fail_messages.append(message)

    def echo(self, message: str) -> None:
        self.echo_messages.append(message)


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

        def plan_tools(self, config, *, root):  # pragma: no cover - not used in this test
            raise NotImplementedError

    monkeypatch.setattr(
        lint_runtime,
        "DEFAULT_LINT_DEPENDENCIES",
        replace(
            lint_runtime.DEFAULT_LINT_DEPENDENCIES,
            orchestrator_factory=lambda registry, discovery, hooks, debug_logger=None: FakeOrchestrator(hooks),
        ),
    )
    monkeypatch.setattr("pyqa.cli.commands.lint.command.detect_tty", lambda: False)

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
    assert "0 diagnostic(s)" in result.stdout


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


def test_only_unknown_tool_fails_fast(tmp_path: Path, monkeypatch) -> None:
    """Ensure ``lint`` exits with an error when ``--only`` cites an unknown tool."""

    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "lint",
            "--only",
            "unknown-tool",
            "--root",
            str(tmp_path),
            "--no-emoji",
        ],
    )

    assert result.exit_code == 1
    combined = (result.stdout + result.stderr).lower()
    assert "unknown tool(s) requested via --only: unknown-tool" in combined


def test_explain_tools_outputs_table(tmp_path: Path, monkeypatch) -> None:
    runner = CliRunner()

    target = tmp_path / "module.py"
    target.write_text("print('hi')\n", encoding="utf-8")

    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        app,
        [
            "lint",
            "--explain-tools",
            "--root",
            str(tmp_path),
            "--no-color",
            "--no-emoji",
        ],
    )

    assert result.exit_code == 0
    assert "Tool Selection Plan" in result.stdout
    assert "Planned" in result.stdout
    assert "pyqa-interfaces" in result.stdout
    assert "pyqa-di" in result.stdout
    assert "pyqa-module-docs" in result.stdout


def test_explain_tools_conflicts_with_tool_info(tmp_path: Path) -> None:
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "lint",
            "--explain-tools",
            "--tool-info",
            "ruff",
            "--root",
            str(tmp_path),
        ],
    )

    assert result.exit_code != 0
    combined_output = result.stdout + result.stderr
    assert "cannot be combined" in combined_output


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

        def plan_tools(self, config, *, root):  # pragma: no cover - unused
            raise NotImplementedError

        def plan_tools(self, config, *, root):  # pragma: no cover - unused
            raise NotImplementedError

    monkeypatch.setattr(
        lint_runtime,
        "DEFAULT_LINT_DEPENDENCIES",
        replace(
            lint_runtime.DEFAULT_LINT_DEPENDENCIES,
            orchestrator_factory=lambda registry, discovery, hooks, debug_logger=None: FakeOrchestrator(hooks),
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
    resolved_tests = tests_dir.resolve()
    resolved_tests = tests_dir.resolve()
    resolved_tests = tests_dir.resolve()
    resolved_tests = tests_dir.resolve()
    resolved_tests = tests_dir.resolve()

    monkeypatch.setattr(lint_module, "build_config", fake_build_config)

    class FakeRunOrchestrator:
        def __init__(self, hooks):
            self._hooks = hooks

        def run(self, config, root):
            return _run(config, root)

        def fetch_all_tools(self, config, root, callback=None):  # pragma: no cover - unused
            return []

        def plan_tools(self, config, *, root):  # pragma: no cover - unused
            raise NotImplementedError

    monkeypatch.setattr(
        lint_runtime,
        "DEFAULT_LINT_DEPENDENCIES",
        replace(
            lint_runtime.DEFAULT_LINT_DEPENDENCIES,
            orchestrator_factory=lambda registry, discovery, hooks, debug_logger=None: FakeRunOrchestrator(hooks),
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
    resolved_tests = (tmp_path / "tests").resolve()
    assert Path("tests") in options.exclude or resolved_tests in options.exclude
    config = captured["config"]
    assert isinstance(config, Config)
    assert any(path == resolved_tests for path in config.file_discovery.excludes)


def test_license_header_linter_reports_issue(tmp_path: Path) -> None:
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

    class _StubLogger:
        def ok(self, message: str) -> None:  # noqa: D401 - stub
            return None

        def warn(self, message: str) -> None:
            return None

        def fail(self, message: str) -> None:
            return None

    state = SimpleNamespace(
        root=tmp_path,
        options=SimpleNamespace(
            target_options=SimpleNamespace(
                root=tmp_path,
                paths=[target],
                dirs=[],
                exclude=[],
                paths_from_stdin=False,
            ),
        ),
        meta=_meta_flags(),
        logger=_StubLogger(),
    )

    report = run_license_header_linter(state, emit_to_logger=False, config=config)
    assert report.outcome.returncode != 0
    assert report.outcome.diagnostics
    first = report.outcome.diagnostics[0]
    assert first.tool == "license-header"
    assert first.code.startswith("license-header:")


def test_suppression_linter_ignores_valid_marker(tmp_path: Path) -> None:
    target = tmp_path / "module.py"
    target.write_text(
        "import os  # noqa: F401 suppression_valid: Import preserves eager plugin registration order\n",
        encoding="utf-8",
    )

    state = _build_stub_state(
        root=tmp_path,
        only=[],
        filters=[],
        check_docstrings=False,
        check_suppressions=True,
        logger=_CapturingLogger(),
        target_paths=[target],
    )

    report = run_suppression_linter(state, emit_to_logger=False)
    assert report.outcome.diagnostics == []


def test_suppression_linter_reports_valid_marker_when_requested(tmp_path: Path) -> None:
    target = tmp_path / "module.py"
    reason = "Import keeps plugin namespace ready before dynamic registration"
    target.write_text(
        f"import os  # noqa: F401 suppression_valid: {reason}\n",
        encoding="utf-8",
    )

    state = _build_stub_state(
        root=tmp_path,
        only=[],
        filters=[],
        check_docstrings=False,
        check_suppressions=True,
        show_valid_suppressions=True,
        logger=_CapturingLogger(),
        target_paths=[target],
    )

    report = run_suppression_linter(state, emit_to_logger=False)
    diagnostics = report.outcome.diagnostics
    assert len(diagnostics) == 1
    diagnostic = diagnostics[0]
    assert diagnostic.severity is Severity.NOTICE
    assert "suppression" in diagnostic.code
    assert reason in diagnostic.message


def test_suppression_linter_requires_sufficient_reason(tmp_path: Path) -> None:
    target = tmp_path / "module.py"
    target.write_text(
        "import os  # noqa: F401 suppression_valid: context matters\n",
        encoding="utf-8",
    )

    state = _build_stub_state(
        root=tmp_path,
        only=[],
        filters=[],
        check_docstrings=False,
        check_suppressions=True,
        logger=_CapturingLogger(),
        target_paths=[target],
    )

    report = run_suppression_linter(state, emit_to_logger=False)
    diagnostics = report.outcome.diagnostics
    assert len(diagnostics) == 1
    assert diagnostics[0].severity is Severity.WARNING
    assert "suppression_valid" in diagnostics[0].message


def test_pyqa_interface_linter_skips_tests(tmp_path: Path) -> None:
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    test_module = tests_dir / "example.py"
    test_module.write_text("import pyqa.reporting\n", encoding="utf-8")

    state = _build_stub_state(
        root=tmp_path,
        only=[],
        filters=[],
        check_docstrings=False,
        logger=_CapturingLogger(),
        target_paths=[test_module],
    )
    state.meta = _meta_flags(pyqa_rules=True)
    report = run_pyqa_interface_linter(state, emit_to_logger=False)
    assert report.outcome.diagnostics == []


def test_pyqa_interface_linter_reports_production_imports(tmp_path: Path) -> None:
    module_path = tmp_path / "service.py"
    module_path.write_text("import pyqa.reporting\n", encoding="utf-8")

    state = _build_stub_state(
        root=tmp_path,
        only=[],
        filters=[],
        check_docstrings=False,
        logger=_CapturingLogger(),
        target_paths=[module_path],
    )
    state.meta = _meta_flags(pyqa_rules=True)
    report = run_pyqa_interface_linter(state, emit_to_logger=False)
    assert report.outcome.diagnostics


def test_python_hygiene_linter_reports_breakpoint(tmp_path: Path) -> None:
    target = tmp_path / "module.py"
    target.write_text("breakpoint()\n", encoding="utf-8")

    config_path = tmp_path / "pyproject.toml"
    config_path.write_text("[tool.pyqa]\n", encoding="utf-8")
    loader = ConfigLoader.for_root(tmp_path)
    config = loader.load_with_trace().config
    config.severity.sensitivity = "maximum"

    state = SimpleNamespace(
        root=tmp_path,
        options=SimpleNamespace(
            target_options=SimpleNamespace(
                root=tmp_path,
                paths=[target],
                dirs=[],
                exclude=[],
                paths_from_stdin=False,
            ),
        ),
        meta=_meta_flags(),
        logger=None,
    )

    report = run_python_hygiene_linter(state, emit_to_logger=False, config=config)
    assert report.outcome.returncode == 1
    assert any("breakpoint" in diagnostic.message.lower() for diagnostic in report.outcome.diagnostics)


def test_file_size_linter_reports_large_file(tmp_path: Path) -> None:
    target = tmp_path / "large.bin"
    target.write_bytes(b"x" * 2048)

    config_path = tmp_path / "pyproject.toml"
    config_path.write_text(
        """
[tool.pyqa.quality]
max_file_size = 1024
warn_file_size = 512
checks = ["file-size"]
""".strip()
        + "\n",
        encoding="utf-8",
    )

    loader = ConfigLoader.for_root(tmp_path)
    config = loader.load_with_trace().config
    config.severity.sensitivity = "maximum"

    state = SimpleNamespace(
        root=tmp_path,
        options=SimpleNamespace(
            target_options=SimpleNamespace(
                root=tmp_path,
                paths=[target],
                dirs=[],
                exclude=[],
                paths_from_stdin=False,
            ),
        ),
        meta=_meta_flags(),
        logger=None,
    )

    report = run_file_size_linter(state, emit_to_logger=False, config=config)
    assert report.outcome.returncode == 1
    assert any("size" in diagnostic.message.lower() for diagnostic in report.outcome.diagnostics)


def test_render_explain_tools_includes_order_and_description() -> None:
    from pyqa.cli.commands.lint.explain import render_explain_tools

    console_stream = StringIO()
    console = Console(file=console_stream, force_terminal=False, color_system=None)

    class _ExplainLogger:
        def __init__(self) -> None:
            self.console = console
            self.ok_messages: list[str] = []

        def ok(self, message: str) -> None:
            self.ok_messages.append(message)

        def warn(self, message: str) -> None:  # pragma: no cover - stub
            self.ok_messages.append(message)

        def fail(self, message: str) -> None:  # pragma: no cover - stub
            self.ok_messages.append(message)

    class _Registry:
        def __init__(self) -> None:
            self._tools = {
                "alpha": SimpleNamespace(description="Alpha internal linter"),
                "beta": SimpleNamespace(description="Beta formatter"),
            }

        def try_get(self, name: str):
            return self._tools.get(name)

    runtime = SimpleNamespace(state=SimpleNamespace(logger=_ExplainLogger()), registry=_Registry())

    selection = SelectionResult(
        ordered=("alpha",),
        decisions=(
            ToolDecision(
                name="alpha",
                family="internal",
                phase="lint",
                action="run",
                reasons=("workspace-match",),
                eligibility=ToolEligibility(
                    name="alpha",
                    family="internal",
                    phase="lint",
                    available=True,
                    requested_via_only=False,
                    language_match=True,
                    extension_match=True,
                    config_match=None,
                    sensitivity_ok=True,
                    pyqa_scope=None,
                    default_enabled=True,
                ),
            ),
            ToolDecision(
                name="beta",
                family="external",
                phase="lint",
                action="skip",
                reasons=("no-language-match",),
                eligibility=ToolEligibility(
                    name="beta",
                    family="external",
                    phase="lint",
                    available=True,
                    requested_via_only=False,
                    language_match=False,
                    extension_match=False,
                    config_match=False,
                    sensitivity_ok=None,
                    pyqa_scope=None,
                    default_enabled=False,
                ),
            ),
        ),
        context=SimpleNamespace(),
    )

    render_explain_tools(runtime, selection)
    output = console_stream.getvalue()
    assert "Order" in output and "Description" in output
    assert "Alpha internal linter" in output
    assert "1" in output


def _build_stub_state(
    *,
    root: Path,
    only: list[str],
    filters: list[str],
    check_docstrings: bool,
    logger,
    target_paths: list[Path] | None = None,
    check_suppressions: bool = False,
    show_valid_suppressions: bool = False,
    check_pyqa_python_hygiene: bool = False,
):
    class _StubOptions:
        def __init__(self, root: Path, only: list[str], filters: list[str], target_paths: list[Path] | None) -> None:
            self.selection_options = SimpleNamespace(only=list(only), filters=list(filters))
            self.target_options = SimpleNamespace(
                root=root,
                paths=list(target_paths or []),
                dirs=[],
                exclude=[],
                paths_from_stdin=False,
            )
            self.execution_options = SimpleNamespace(
                runtime=SimpleNamespace(
                    no_cache=False,
                    cache_dir=root / ".lint-cache",
                )
            )
            self._provided = frozenset()

        @property
        def provided(self) -> frozenset[str]:
            return self._provided

        def with_added_provided(self, *flags: str) -> None:
            updated = set(self._provided)
            updated.update(flag for flag in flags if flag)
            self._provided = frozenset(updated)

    return SimpleNamespace(
        root=root,
        options=_StubOptions(root, only, filters, target_paths),
        meta=_meta_flags(
            check_docstrings=check_docstrings,
            check_suppressions=check_suppressions,
            show_valid_suppressions=show_valid_suppressions,
            check_pyqa_python_hygiene=check_pyqa_python_hygiene,
        ),
        logger=logger,
        suppressions=SuppressionRegistry(root),
    )


def test_activate_internal_linters_meta_sets_only(tmp_path: Path) -> None:
    logger = _CapturingLogger()
    state = _build_stub_state(
        root=tmp_path,
        only=[],
        filters=[],
        check_docstrings=True,
        logger=logger,
        target_paths=[tmp_path / "module.py"],
    )

    lint_module._activate_internal_linters(state)

    assert state.options.selection_options.only == ["docstrings"]
    provided = state.options.provided
    assert "only" in provided
    assert PROVIDED_FLAG_INTERNAL_LINTERS in provided


def test_activate_internal_linters_no_meta(tmp_path: Path) -> None:
    logger = _CapturingLogger()
    state = _build_stub_state(
        root=tmp_path,
        only=[],
        filters=[],
        check_docstrings=False,
        logger=logger,
    )

    lint_module._activate_internal_linters(state)

    assert state.options.selection_options.only == []
    assert PROVIDED_FLAG_INTERNAL_LINTERS not in state.options.provided


def test_activate_internal_linters_idempotent(tmp_path: Path) -> None:
    logger = _CapturingLogger()
    state = _build_stub_state(
        root=tmp_path,
        only=[],
        filters=[],
        check_docstrings=True,
        logger=logger,
    )

    lint_module._activate_internal_linters(state)
    lint_module._activate_internal_linters(state)

    assert state.options.selection_options.only == ["docstrings"]


def test_ensure_internal_tools_registered(tmp_path: Path) -> None:
    registry = ToolRegistry()
    logger = _CapturingLogger()
    target = tmp_path / "module.py"
    target.write_text("print('hello')\\n", encoding="utf-8")
    state = _build_stub_state(
        root=tmp_path,
        only=[],
        filters=[],
        check_docstrings=False,
        logger=logger,
        target_paths=[target],
    )

    config = ConfigLoader.for_root(tmp_path).load_with_trace().config
    ensure_internal_tools_registered(registry=registry, state=state, config=config)
    ensure_internal_tools_registered(registry=registry, state=state, config=config)

    internal_tool = registry.try_get("docstrings")
    assert internal_tool is not None
    action = internal_tool.actions[0]
    assert action.is_internal

    context = ToolContext(cfg=config, root=tmp_path, files=tuple(), settings={})
    outcome = action.internal_runner(context)
    assert outcome.tool == "docstrings"
    patterns = config.output.tool_filters.get("docstrings")
    assert patterns is not None
    expected_pattern = r"^docstrings, (?:.+/)?tests?/.*$"
    assert patterns.count(expected_pattern) == 1


def test_lint_meta_normal_applies_defaults(monkeypatch, tmp_path: Path) -> None:
    runner = CliRunner()
    captured: dict[str, Any] = {}

    original_build_config = lint_module.build_config

    def fake_build_config(options):
        captured["options"] = options
        return original_build_config(options)

    tests_dir = tmp_path / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    resolved_tests = tests_dir.resolve()

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
            orchestrator_factory=lambda registry, discovery, hooks, debug_logger=None: FakeOrchestrator(hooks),
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
    assert Path("tests") in options.exclude or resolved_tests in options.exclude
    assert "internal_linters" in options.provided
    config = captured["config"]
    assert isinstance(config, Config)
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
    monkeypatch.setattr(lint_module, "detect_tty", lambda: True)

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

    def _factory(registry, discovery, hooks, debug_logger=None):
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
    assert any(
        event[0] == "update" and event[2] == 4 for event in records
    ), "progress total should include tool actions and extra phases"
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
    sorted_options = sorted(
        options_section,
        key=lambda entry: _display_primary_option(entry[0]),
    )
    assert sorted_options == expected


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


def _display_primary_option(display: str) -> str:
    """Identify the canonical option token extracted from CLI help text."""

    candidates = [segment.strip() for segment in display.split(",") if segment.strip()]
    for candidate in candidates:
        token = candidate.split(" ", 1)[0]
        if token.startswith("--"):
            return token.lstrip("-").lower()
    if candidates:
        token = candidates[0].split(" ", 1)[0]
        return token.lstrip("-").lower()
    return display.strip().lower()
