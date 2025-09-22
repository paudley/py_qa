# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Tests for reporting emitters."""

# pylint: disable=missing-function-docstring

import json
from pathlib import Path

from pyqa.models import Diagnostic, RunResult, ToolOutcome
from pyqa.reporting.emitters import (
    write_json_report,
    write_pr_summary,
    write_sarif_report,
)
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
