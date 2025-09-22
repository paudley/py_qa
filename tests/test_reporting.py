# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Tests for reporting emitters."""

# pylint: disable=missing-function-docstring

import json
from pathlib import Path

from pyqa.config import OutputConfig
from pyqa.models import Diagnostic, RunResult, ToolOutcome
from pyqa.reporting.emitters import (
    write_json_report,
    write_pr_summary,
    write_sarif_report,
)
from pyqa.reporting.formatters import render
from pyqa.severity import Severity


def _run_result(tmp_path: Path) -> RunResult:
    diag = Diagnostic(
        file="src/app.py",
        line=10,
        column=2,
        severity=Severity.ERROR,
        message="bad things",
        tool="ruff",
        code="F401",
    )
    diag2 = Diagnostic(
        file="src/app.py",
        line=20,
        column=None,
        severity=Severity.WARNING,
        message="meh",
        tool="ruff",
        code="W000",
    )
    outcome = ToolOutcome(
        tool="ruff",
        action="lint",
        returncode=1,
        stdout="",
        stderr="",
        diagnostics=[diag, diag2],
    )
    return RunResult(
        root=tmp_path,
        files=[tmp_path / "src" / "app.py"],
        outcomes=[outcome],
        tool_versions={"ruff": "ruff 1.0.0"},
    )


def test_write_json_report(tmp_path: Path) -> None:
    result = _run_result(tmp_path)
    dest = tmp_path / "report.json"
    write_json_report(result, dest)

    data = json.loads(dest.read_text(encoding="utf-8"))
    assert data["outcomes"][0]["diagnostics"][0]["code"] == "F401"


def test_write_sarif_report(tmp_path: Path) -> None:
    result = _run_result(tmp_path)
    dest = tmp_path / "report.sarif"
    write_sarif_report(result, dest)

    data = json.loads(dest.read_text(encoding="utf-8"))
    assert data["version"] == "2.1.0"
    runs = data["runs"]
    assert runs[0]["tool"]["driver"]["name"] == "ruff"
    assert runs[0]["tool"]["driver"]["version"] == "ruff 1.0.0"
    assert runs[0]["results"][0]["ruleId"] == "F401"


def test_write_pr_summary(tmp_path: Path) -> None:
    result = _run_result(tmp_path)
    dest = tmp_path / "summary.md"
    write_pr_summary(result, dest, limit=10)

    content = dest.read_text(encoding="utf-8")
    assert "Lint Summary" in content
    assert "ERROR" in content
    assert "bad things" in content
    assert "meh" in content


def test_write_pr_summary_with_filter_and_template(tmp_path: Path) -> None:
    result = _run_result(tmp_path)
    dest = tmp_path / "summary.md"
    write_pr_summary(
        result,
        dest,
        limit=5,
        min_severity="error",
        template="* {tool}:{code} -> {message}",
    )

    content = dest.read_text(encoding="utf-8")
    assert "F401" in content
    assert "W000" not in content
    assert "ruff:F401" in content


def test_render_concise_shows_diagnostics_for_failures(tmp_path: Path, capsys) -> None:
    result = _run_result(tmp_path)
    config = OutputConfig(color=False, emoji=False)
    render(result, config)
    output_lines = [line.strip() for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert output_lines == [
        "ruff, src/app.py:10, F401, bad things",
        "ruff, src/app.py:20, W000, meh",
        "Failed — 2 diagnostic(s) across 1 file(s); 1 failing action(s) out of 1",
    ]


def test_render_concise_fallbacks_to_stderr(tmp_path: Path, capsys) -> None:
    outcome = ToolOutcome(
        tool="black",
        action="check",
        returncode=1,
        stdout="",
        stderr="line1\nline2\nline3\nline4\nline5\nline6\nline7\nline8\nline9\nline10\nline11\n",
        diagnostics=[],
    )
    result = RunResult(
        root=tmp_path,
        files=[],
        outcomes=[outcome],
        tool_versions={},
    )
    config = OutputConfig(color=False, emoji=False)
    render(result, config)
    output_lines = [line.strip() for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert output_lines == [
        "Failed — 0 diagnostic(s) across 0 file(s); 1 failing action(s) out of 1",
    ]


def test_render_concise_sorted_and_deduped(tmp_path: Path, capsys) -> None:
    diag1 = Diagnostic(
        file="b.py",
        line=2,
        column=None,
        severity=Severity.ERROR,
        message="issue b",
        tool="ruff",
        code="F001",
        function="resolve_b",
    )
    diag_dup = Diagnostic(
        file="b.py",
        line=2,
        column=None,
        severity=Severity.ERROR,
        message="issue b",
        tool="ruff",
        code="F001",
        function="resolve_b",
    )
    diag2 = Diagnostic(
        file="a.py",
        line=5,
        column=None,
        severity=Severity.WARNING,
        message="warn a",
        tool="bandit",
        code="B001",
    )
    diag3 = Diagnostic(
        file="a.py",
        line=3,
        column=None,
        severity=Severity.WARNING,
        message="warn early",
        tool="bandit",
        code="B000",
        function="check_func",
    )
    outcome = ToolOutcome(
        tool="ruff",
        action="lint",
        returncode=1,
        stdout="",
        stderr="",
        diagnostics=[diag1, diag_dup, diag2, diag3],
    )
    result = RunResult(
        root=tmp_path,
        files=[],
        outcomes=[outcome],
        tool_versions={},
    )
    config = OutputConfig(color=False, emoji=False)
    render(result, config)
    output_lines = [line.strip() for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert output_lines == [
        "bandit, a.py:3:check_func, B000, warn early",
        "bandit, a.py:5, B001, warn a",
        "ruff, b.py:2:resolve_b, F001, issue b",
        "Failed — 3 diagnostic(s) across 0 file(s); 1 failing action(s) out of 1",
    ]


def test_render_concise_normalizes_paths(tmp_path: Path, capsys) -> None:
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    abs_path = src_dir / "pkg" / "module.py"
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    diag = Diagnostic(
        file=str(abs_path),
        line=7,
        column=None,
        severity=Severity.ERROR,
        message="absolute issue",
        tool="mypy",
        code="attr-defined",
        function="resolve_value",
    )
    outcome = ToolOutcome(
        tool="mypy",
        action="type-check",
        returncode=1,
        stdout="",
        stderr="",
        diagnostics=[diag],
    )
    result = RunResult(
        root=tmp_path,
        files=[],
        outcomes=[outcome],
        tool_versions={},
    )
    config = OutputConfig(color=False, emoji=False)
    render(result, config)
    output_lines = [line.strip() for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert output_lines == [
        "mypy, src/pkg/module.py:7:resolve_value, attr-defined, absolute issue",
        "Failed — 1 diagnostic(s) across 0 file(s); 1 failing action(s) out of 1",
    ]
