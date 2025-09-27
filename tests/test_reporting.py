# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Tests for reporting emitters."""

import json
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from pyqa.annotations import AnnotationEngine, MessageSpan
from pyqa.config import OutputConfig
from pyqa.models import Diagnostic, RunResult, ToolOutcome
from pyqa.reporting.advice import AdviceBuilder, AdviceEntry, AdviceCategory, generate_advice
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
    result.analysis["refactor_navigator"] = [
        {
            "file": "src/app.py",
            "function": "main",
            "issue_tags": {"complexity": 2},
            "size": 12,
            "complexity": 4,
            "diagnostics": [],
        },
    ]
    dest = tmp_path / "report.json"
    write_json_report(result, dest)

    data = json.loads(dest.read_text(encoding="utf-8"))
    assert data["outcomes"][0]["diagnostics"][0]["code"] == "F401"
    assert data["analysis"]["refactor_navigator"][0]["function"] == "main"


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


def test_write_pr_summary_can_include_advice(tmp_path: Path) -> None:
    module_path = tmp_path / "src" / "pkg" / "module.py"
    module_path.parent.mkdir(parents=True, exist_ok=True)
    module_path.write_text(
        """def build_widget(foo, bar):\n    return foo + bar\n""",
        encoding="utf-8",
    )

    diagnostics = [
        _advice_diag(
            file="src/pkg/module.py",
            tool="ruff",
            code="ANN001",
            message="Missing type annotation for function argument foo",
            function="build_widget",
        ),
        _advice_diag(
            file="src/pkg/module.py",
            tool="ruff",
            code="ANN001",
            message="Missing type annotation for function argument bar",
            function="build_widget",
        ),
        _advice_diag(
            file="src/pkg/module.py",
            tool="ruff",
            code="ANN201",
            message="Missing return type annotation for public function build_widget",
            function="build_widget",
        ),
    ]

    outcome = ToolOutcome(
        tool="ruff",
        action="lint",
        returncode=1,
        stdout="",
        stderr="",
        diagnostics=diagnostics,
    )
    result = RunResult(
        root=tmp_path,
        files=[module_path],
        outcomes=[outcome],
        tool_versions={},
    )
    dest = tmp_path / "summary.md"
    write_pr_summary(result, dest, include_advice=True, advice_limit=3)

    content = dest.read_text(encoding="utf-8")
    assert "## SOLID Advice" in content
    assert "- **Types:** introduce explicit annotations in src/pkg/module.py" in content


def test_write_pr_summary_allows_advice_template_override(tmp_path: Path) -> None:
    module_path = tmp_path / "src" / "pkg" / "module.py"
    module_path.parent.mkdir(parents=True, exist_ok=True)
    module_path.write_text(
        """def build_widget(foo, bar):\n    return foo + bar\n""",
        encoding="utf-8",
    )

    diagnostics = [
        _advice_diag(
            file="src/pkg/module.py",
            tool="ruff",
            code="ANN001",
            message="Missing type annotation for function argument foo",
            function="build_widget",
        ),
        _advice_diag(
            file="src/pkg/module.py",
            tool="ruff",
            code="ANN201",
            message="Missing return type annotation for public function build_widget",
            function="build_widget",
        ),
        _advice_diag(
            file="src/pkg/module.py",
            tool="ruff",
            code="ANN202",
            message="Missing type annotation for function argument baz",
            function="build_widget",
        ),
    ]

    outcome = ToolOutcome(
        tool="ruff",
        action="lint",
        returncode=1,
        stdout="",
        stderr="",
        diagnostics=diagnostics,
    )
    result = RunResult(
        root=tmp_path,
        files=[module_path],
        outcomes=[outcome],
        tool_versions={},
    )
    dest = tmp_path / "summary.md"
    write_pr_summary(
        result,
        dest,
        include_advice=True,
        advice_limit=2,
        advice_template="> [{category}] {body}",
    )

    content = dest.read_text(encoding="utf-8")
    assert "> [Types] introduce explicit annotations" in content


def test_write_pr_summary_template_can_reference_advice_summary(tmp_path: Path) -> None:
    module_path = tmp_path / "src" / "pkg" / "module.py"
    module_path.parent.mkdir(parents=True, exist_ok=True)
    module_path.write_text(
        """
def build_widget(foo, bar, baz):
    return foo + bar + baz
""".strip(),
        encoding="utf-8",
    )

    diagnostics = [
        _advice_diag(
            file="src/pkg/module.py",
            tool="ruff",
            code="ANN001",
            message="Missing type annotation for function argument foo",
            function="build_widget",
        ),
        _advice_diag(
            file="src/pkg/module.py",
            tool="ruff",
            code="ANN001",
            message="Missing type annotation for function argument bar",
            function="build_widget",
        ),
        _advice_diag(
            file="src/pkg/module.py",
            tool="ruff",
            code="ANN201",
            message="Missing return type annotation for public function build_widget",
            function="build_widget",
        ),
    ]

    outcome = ToolOutcome(
        tool="ruff",
        action="lint",
        returncode=1,
        stdout="",
        stderr="",
        diagnostics=diagnostics,
    )
    result = RunResult(
        root=tmp_path,
        files=[module_path],
        outcomes=[outcome],
        tool_versions={},
    )
    dest = tmp_path / "summary.md"
    write_pr_summary(
        result,
        dest,
        template="- {code}: {message} (Top: {advice_primary_category})",
        advice_limit=2,
    )

    content = dest.read_text(encoding="utf-8")
    assert "Top: Types" in content


def test_write_pr_summary_supports_custom_advice_builder(tmp_path: Path) -> None:
    module_path = tmp_path / "src" / "pkg" / "module.py"
    module_path.parent.mkdir(parents=True, exist_ok=True)
    module_path.write_text("def build(foo, bar):\n    return foo + bar\n", encoding="utf-8")

    diagnostics = [
        _advice_diag(
            file="src/pkg/module.py",
            tool="ruff",
            code="ANN001",
            message="Missing type annotation for function argument foo",
            function="build",
        ),
        _advice_diag(
            file="src/pkg/module.py",
            tool="ruff",
            code="ANN201",
            message="Missing return type annotation for public function build",
            function="build",
        ),
        _advice_diag(
            file="src/pkg/module.py",
            tool="ruff",
            code="ANN001",
            message="Missing type annotation for function argument bar",
            function="build",
        ),
    ]

    outcome = ToolOutcome(
        tool="ruff",
        action="lint",
        returncode=1,
        stdout="",
        stderr="",
        diagnostics=diagnostics,
    )
    result = RunResult(
        root=tmp_path,
        files=[module_path],
        outcomes=[outcome],
        tool_versions={},
    )
    dest = tmp_path / "summary.md"

    def builder(entries: Sequence[AdviceEntry]) -> Sequence[str]:
        if not entries:
            return []
        body = ", ".join(f"{entry.category}:{entry.body}" for entry in entries[:1])
        return ["", "## Custom Advice", "", f"* {body}"]

    write_pr_summary(
        result,
        dest,
        include_advice=True,
        advice_section_builder=builder,
    )

    content = dest.read_text(encoding="utf-8")
    assert "## Custom Advice" in content
    assert "Types:" in content


def test_write_pr_summary_custom_builder_respects_severity(tmp_path: Path) -> None:
    module_path = tmp_path / "src" / "pkg" / "module.py"
    module_path.parent.mkdir(parents=True, exist_ok=True)
    module_path.write_text(
        "def build(foo, bar, baz):\n    return foo + bar + baz\n",
        encoding="utf-8",
    )

    diagnostics = [
        _advice_diag(
            file="src/pkg/module.py",
            tool="ruff",
            code="ANN001",
            message="Missing type annotation for function argument foo",
            function="build",
            severity=Severity.ERROR,
        ),
        _advice_diag(
            file="src/pkg/module.py",
            tool="ruff",
            code="ANN001",
            message="Missing type annotation for function argument bar",
            function="build",
            severity=Severity.ERROR,
        ),
        _advice_diag(
            file="src/pkg/module.py",
            tool="ruff",
            code="ANN201",
            message="Missing return type annotation for public function build",
            function="build",
            severity=Severity.ERROR,
        ),
        _advice_diag(
            file="src/pkg/module.py",
            tool="ruff",
            code="ANN001",
            message="Missing type annotation for function argument baz",
            function="build",
            severity=Severity.WARNING,
        ),
    ]

    outcome = ToolOutcome(
        tool="ruff",
        action="lint",
        returncode=1,
        stdout="",
        stderr="",
        diagnostics=diagnostics,
    )
    result = RunResult(
        root=tmp_path,
        files=[module_path],
        outcomes=[outcome],
        tool_versions={},
    )
    dest = tmp_path / "summary.md"

    captured: dict[str, int] = {"count": -1}

    def builder(entries: Sequence[AdviceEntry]) -> Sequence[str]:
        captured["count"] = len(entries)
        if not entries:
            return []
        return ["", "## Severity Advice", "", f"* total={len(entries)}"]

    write_pr_summary(
        result,
        dest,
        include_advice=True,
        min_severity="error",
        advice_limit=5,
        advice_section_builder=builder,
    )

    content = dest.read_text(encoding="utf-8")
    assert "## Severity Advice" in content
    assert "total=1" in content
    assert "baz" not in content
    assert captured["count"] == 1


def test_write_pr_summary_advice_integration_multiple_tools(tmp_path: Path) -> None:
    pkg_dir = tmp_path / "src" / "pkg"
    pkg_dir.mkdir(parents=True, exist_ok=True)
    module_path = pkg_dir / "module.py"
    module_path.write_text(
        """
def complex_func():
    for i in range(3):
        if i % 2:
            print(i)


def typed_func(arg1, arg2):
    return arg1 + arg2
""".strip(),
        encoding="utf-8",
    )

    diagnostics = [
        _advice_diag(
            file="src/pkg/module.py",
            tool="pylint",
            code="R0915",
            message="R0915 Too many statements",
            function="complex_func",
            severity=Severity.ERROR,
        ),
        _advice_diag(
            file="src/pkg/module.py",
            tool="ruff",
            code="ANN001",
            message="Missing type annotation for function argument arg1",
            function="typed_func",
        ),
        _advice_diag(
            file="src/pkg/module.py",
            tool="ruff",
            code="ANN201",
            message="Missing return type annotation for public function typed_func",
            function="typed_func",
        ),
        _advice_diag(
            file="src/pkg/module.py",
            tool="ruff",
            code="ANN202",
            message="Missing type annotation for function argument arg2",
            function="typed_func",
        ),
    ]

    pylint_outcome = ToolOutcome(
        tool="pylint",
        action="lint",
        returncode=1,
        stdout="",
        stderr="",
        diagnostics=[diagnostics[0]],
    )
    ruff_outcome = ToolOutcome(
        tool="ruff",
        action="lint",
        returncode=1,
        stdout="",
        stderr="",
        diagnostics=diagnostics[1:],
    )
    result = RunResult(
        root=tmp_path,
        files=[module_path],
        outcomes=[pylint_outcome, ruff_outcome],
        tool_versions={},
    )

    dest = tmp_path / "summary.md"
    captured_entries: list[Sequence[AdviceEntry]] = []

    def builder(entries: Sequence[AdviceEntry]) -> Sequence[str]:
        captured_entries.append(entries)
        if not entries:
            return []
        return [
            "",
            "## Custom Integration Advice",
            "",
            *[f"* {entry.category}: {entry.body}" for entry in entries[:2]],
        ]

    write_pr_summary(
        result,
        dest,
        include_advice=True,
        advice_limit=3,
        template="- {tool}:{code} {message} | Top:{advice_primary_category}",
        advice_section_builder=builder,
    )

    content = dest.read_text(encoding="utf-8")
    assert "Top:Refactor priority" in content
    assert "## Custom Integration Advice" in content
    assert captured_entries
    latest_entries = captured_entries[-1]
    assert len(latest_entries) >= 2
    categories = {entry.category for entry in latest_entries}
    assert "Refactor priority" in categories
    assert "Types" in categories


def test_render_concise_shows_diagnostics_for_failures(tmp_path: Path, capsys) -> None:
    result = _run_result(tmp_path)
    config = OutputConfig(color=False, emoji=False)
    render(result, config)
    output_lines = [line.strip() for line in capsys.readouterr().out.splitlines() if line.strip()]
    panel_start = next(
        (idx for idx, line in enumerate(output_lines) if line.startswith("╭")),
        -1,
    )
    assert panel_start != -1
    panel_end = next(
        (idx for idx in range(panel_start, len(output_lines)) if output_lines[idx].startswith("╰")),
        -1,
    )
    assert panel_end != -1
    panel_lines = output_lines[panel_start : panel_end + 1]
    assert "Files" in " ".join(panel_lines)
    normalised = [", ".join(part.strip() for part in line.split(",")) for line in output_lines[:2]]
    assert normalised == [
        "ruff, src/app.py:10, F401, bad things",
        "ruff, src/app.py:20, W000, meh",
    ]
    assert output_lines[-1] == (
        "Failed — 2 diagnostic(s) across 1 file(s); 1 failing action(s) out of 1"
    )


def test_render_concise_omits_stats_when_disabled(tmp_path: Path, capsys) -> None:
    result = _run_result(tmp_path)
    config = OutputConfig(color=False, emoji=False, show_stats=False)
    render(result, config)
    output_lines = [line.strip() for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert all(not line.startswith("╭") for line in output_lines)
    normalised = [", ".join(part.strip() for part in line.split(",")) for line in output_lines[:2]]
    assert normalised == [
        "ruff, src/app.py:10, F401, bad things",
        "ruff, src/app.py:20, W000, meh",
    ]
    assert output_lines[-1] == (
        "Failed — 2 diagnostic(s) across 1 file(s); 1 failing action(s) out of 1"
    )


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
    panel_lines = [
        line
        for line in output_lines
        if line.startswith("╭") or line.startswith("│") or line.startswith("╰")
    ]
    assert panel_lines
    assert output_lines[-1] == (
        "Failed — 0 diagnostic(s) across 0 file(s); 1 failing action(s) out of 1"
    )


def test_render_concise_trims_code_prefix(tmp_path: Path, capsys) -> None:
    diag = Diagnostic(
        file="mod.py",
        line=7,
        column=None,
        severity=Severity.WARNING,
        message="C0415: import outside toplevel",
        tool="pylint",
        code="C0415",
    )
    outcome = ToolOutcome(
        tool="pylint",
        action="lint",
        returncode=1,
        stdout="",
        stderr="",
        diagnostics=[diag],
    )
    result = RunResult(
        root=tmp_path,
        files=[tmp_path / "mod.py"],
        outcomes=[outcome],
        tool_versions={},
    )
    config = OutputConfig(color=False, emoji=False)
    render(result, config)
    output_lines = [line.strip() for line in capsys.readouterr().out.splitlines() if line.strip()]
    row = next(line for line in output_lines if line.startswith("pylint"))
    parts = [part.strip() for part in row.split(",")]
    assert parts[0] == "pylint"
    assert parts[1] == "mod.py:7"
    assert parts[2] == "C0415"
    assert parts[3] == "import outside toplevel"


def test_render_concise_does_not_pad_codes(tmp_path: Path, capsys) -> None:
    diag_short = Diagnostic(
        file="pkg/mod.py",
        line=4,
        column=None,
        severity=Severity.ERROR,
        message="short code",
        tool="flake8",
        code="E1",
    )
    diag_long = Diagnostic(
        file="pkg/mod.py",
        line=5,
        column=None,
        severity=Severity.ERROR,
        message="long code",
        tool="flake8",
        code="ERROR-LONG-CODE",
    )
    outcome = ToolOutcome(
        tool="flake8",
        action="lint",
        returncode=1,
        stdout="",
        stderr="",
        diagnostics=[diag_short, diag_long],
    )
    result = RunResult(
        root=tmp_path,
        files=[tmp_path / "pkg" / "mod.py"],
        outcomes=[outcome],
        tool_versions={},
    )
    config = OutputConfig(color=False, emoji=False)
    render(result, config)
    raw_lines = capsys.readouterr().out.splitlines()
    short_line = next(line for line in raw_lines if "short code" in line)
    long_line = next(line for line in raw_lines if "long code" in line)

    short_code_segment = short_line.split(",")[2]
    long_code_segment = long_line.split(",")[2]

    assert short_code_segment == " E1"
    assert long_code_segment == " ERROR-LONG-CODE"


def test_render_concise_trims_code_whitespace(tmp_path: Path, capsys) -> None:
    diag = Diagnostic(
        file="src/typer_ext.py",
        line=59,
        column=None,
        severity=Severity.ERROR,
        message="Line too long (130/120)",
        tool="pylint",
        code="C0301   ",
        function="command",
    )
    outcome = ToolOutcome(
        tool="pylint",
        action="lint",
        returncode=1,
        stdout="",
        stderr="",
        diagnostics=[diag],
    )
    result = RunResult(
        root=tmp_path,
        files=[tmp_path / "src" / "typer_ext.py"],
        outcomes=[outcome],
        tool_versions={},
    )
    config = OutputConfig(color=False, emoji=False)
    render(result, config)
    output_lines = [line.strip() for line in capsys.readouterr().out.splitlines() if line.strip()]
    row = next(line for line in output_lines if line.startswith("pylint"))
    parts = [part.strip() for part in row.split(",")]
    assert parts == [
        "pylint",
        "src/typer_ext.py:59:command",
        "C0301",
        "Line too long (130/120)",
    ]


def test_render_pretty_trims_code_whitespace(tmp_path: Path, capsys) -> None:
    diag = Diagnostic(
        file="src/typer_ext.py",
        line=59,
        column=None,
        severity=Severity.ERROR,
        message="Line too long (130/120)",
        tool="pylint",
        code="C0301   ",
        function="command",
    )
    outcome = ToolOutcome(
        tool="pylint",
        action="lint",
        returncode=1,
        stdout="",
        stderr="",
        diagnostics=[diag],
    )
    result = RunResult(
        root=tmp_path,
        files=[tmp_path / "src" / "typer_ext.py"],
        outcomes=[outcome],
        tool_versions={},
    )
    config = OutputConfig(color=False, emoji=False, output="pretty")
    render(result, config)
    output = capsys.readouterr().out.splitlines()
    diag_line = next(line for line in output if "Line too long" in line)
    assert diag_line.strip().endswith("Line too long (130/120) [C0301]")


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
    panel_start = next(
        (idx for idx, line in enumerate(output_lines) if line.startswith("╭")),
        -1,
    )
    assert panel_start != -1
    normalised = [", ".join(part.strip() for part in line.split(",")) for line in output_lines[:3]]
    assert normalised == [
        "bandit, a.py:3:check_func, B000, warn early",
        "bandit, a.py:5, B001, warn a",
        "ruff, b.py:2:resolve_b, F001, issue b",
    ]
    assert output_lines[-1] == (
        "Failed — 3 diagnostic(s) across 0 file(s); 1 failing action(s) out of 1"
    )


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
    panel_start = next(
        (idx for idx, line in enumerate(output_lines) if line.startswith("╭")),
        -1,
    )
    assert panel_start != -1
    assert output_lines[0] == (
        "mypy, src/pkg/module.py:7:resolve_value, attr-defined, absolute issue"
    )
    assert output_lines[-1] == (
        "Failed — 1 diagnostic(s) across 0 file(s); 1 failing action(s) out of 1"
    )


def test_render_concise_sanitizes_function_field(tmp_path: Path, capsys) -> None:
    noisy = Diagnostic(
        file="pkg/mod.py",
        line=4,
        column=None,
        severity=Severity.WARNING,
        message="multiline function noise",
        tool="pyright",
        code="reportGeneralTypeIssues",
        function="# SPDX comment\nshould not leak",
    )
    clean = Diagnostic(
        file="pkg/mod.py",
        line=9,
        column=None,
        severity=Severity.ERROR,
        message="legit",
        tool="pyright",
        code="reportUndefinedVariable",
        function="Module.resolve",
    )
    outcome = ToolOutcome(
        tool="pyright",
        action="check",
        returncode=1,
        stdout="",
        stderr="",
        diagnostics=[noisy, clean],
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
    assert output_lines[0] == (
        "pyright, pkg/mod.py:4, reportGeneralTypeIssues, multiline function noise"
    )
    assert output_lines[1] == (
        "pyright, pkg/mod.py:9:Module.resolve, reportUndefinedVariable, legit"
    )


def test_render_concise_merges_argument_annotations(tmp_path: Path, capsys) -> None:
    details = ["cfg", "console", "root", "tool_name"]
    diagnostics = [
        Diagnostic(
            file="tests/test_tool_info.py",
            line=21,
            column=None,
            severity=Severity.WARNING,
            message=f"Missing type annotation for function argument `{detail}`",
            tool="ruff",
            code="ANN001",
            function="fake_run_tool_info",
        )
        for detail in details
    ]
    outcome = ToolOutcome(
        tool="ruff",
        action="lint",
        returncode=1,
        stdout="",
        stderr="",
        diagnostics=diagnostics,
    )
    result = RunResult(
        root=tmp_path,
        files=[tmp_path / "tests" / "test_tool_info.py"],
        outcomes=[outcome],
        tool_versions={},
    )
    config = OutputConfig(color=False, emoji=False)
    render(result, config)
    output_lines = [line.strip() for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert output_lines[0] == (
        "ruff, tests/test_tool_info.py:21:fake_run_tool_info, ANN001, Missing type annotation for function argument cfg, console, root, tool_name"
    )


def _advice_diag(
    *,
    file: str,
    tool: str,
    code: str,
    message: str,
    severity: Severity = Severity.WARNING,
    function: str | None = None,
) -> Diagnostic:
    return Diagnostic(
        file=file,
        line=1,
        column=None,
        severity=severity,
        message=message,
        tool=tool,
        code=code,
        function=function,
    )


def test_render_advice_panel_highlights_structural_gaps(tmp_path: Path, capsys) -> None:
    diagnostics = [
        _advice_diag(
            file="src/pkg/module.py",
            tool="ruff",
            code="D100",
            message="D100 Missing docstring",
        ),
        _advice_diag(
            file="src/pkg/module.py",
            tool="ruff",
            code="D101",
            message="D101 Missing docstring",
        ),
        _advice_diag(
            file="src/pkg/module.py",
            tool="ruff",
            code="D102",
            message="D102 Missing docstring",
        ),
        _advice_diag(
            file="src/pkg/module.py",
            tool="ruff",
            code="ANN001",
            message="ANN001 Missing type annotation",
        ),
        _advice_diag(
            file="src/pkg/module.py",
            tool="ruff",
            code="ANN201",
            message="ANN201 Missing type annotation",
        ),
        _advice_diag(
            file="src/pkg/module.py",
            tool="ruff",
            code="ANN202",
            message="ANN202 Missing type annotation",
        ),
        _advice_diag(
            file="src/pkg/__init__.py",
            tool="ruff",
            code="INP001",
            message="INP001 Missing package init",
        ),
        _advice_diag(
            file="src/pkg/private_use.py",
            tool="pyright",
            code="reportPrivateImportUsage",
            message="Importing private module",
        ),
        _advice_diag(
            file="src/pkg/data.py",
            tool="ruff",
            code="PLR2004",
            message="PLR2004 Magic number",
        ),
        _advice_diag(
            file="src/pkg/data.py",
            tool="ruff",
            code="PLR2004",
            message="PLR2004 Magic number second",
        ),
    ]
    outcome = ToolOutcome(
        tool="composite",
        action="lint",
        returncode=1,
        stdout="",
        stderr="",
        diagnostics=diagnostics,
    )
    result = RunResult(
        root=tmp_path,
        files=[tmp_path / "src" / "pkg" / "module.py"],
        outcomes=[outcome],
        tool_versions={},
    )
    config = OutputConfig(color=False, emoji=False, advice=True, show_stats=False)
    render(result, config)
    output = capsys.readouterr().out
    assert "SOLID Advice" in output
    assert "Documentation: add module/function docstrings" in output
    assert "Types: introduce explicit annotations" in output
    assert "Packaging: add an __init__.py to src/pkg" in output
    assert "Encapsulation: expose public APIs" in output
    assert "Constants: move magic numbers" in output


def test_render_advice_summarises_annotations_and_magic(tmp_path: Path, capsys) -> None:
    diagnostics: list[Diagnostic] = []
    for idx in range(6):
        file_path = f"src/pkg/module{idx}.py"
        for detail in ("alpha", "beta", "gamma"):
            diagnostics.append(
                Diagnostic(
                    file=file_path,
                    line=idx + 1,
                    column=None,
                    severity=Severity.WARNING,
                    message=f"Missing type annotation for function argument `{detail}`",
                    tool="ruff",
                    code="ANN001",
                    function="heavy_worker",
                ),
            )
    for idx in range(6):
        file_path = f"src/pkg/config{idx}.py"
        diagnostics.append(
            Diagnostic(
                file=file_path,
                line=idx + 10,
                column=None,
                severity=Severity.WARNING,
                message="Magic constant 42",
                tool="ruff",
                code="PLR2004",
                function="configure",
            ),
        )
        diagnostics.append(
            Diagnostic(
                file=file_path,
                line=idx + 11,
                column=None,
                severity=Severity.WARNING,
                message="Magic constant 7",
                tool="ruff",
                code="PLR2004",
                function="configure",
            ),
        )
    outcome = ToolOutcome(
        tool="ruff",
        action="lint",
        returncode=1,
        stdout="",
        stderr="",
        diagnostics=diagnostics,
    )
    result = RunResult(
        root=tmp_path,
        files=[tmp_path / "src" / "pkg" / "module0.py"],
        outcomes=[outcome],
        tool_versions={},
    )
    config = OutputConfig(color=False, emoji=False, advice=True, show_stats=False)
    render(result, config)
    output = capsys.readouterr().out
    type_lines = [
        line for line in output.splitlines() if "Types: introduce explicit annotations" in line
    ]
    assert len(type_lines) == 1
    builder = AdviceBuilder()
    advice_entries = generate_advice(
        [
            (
                diag.file or "",
                diag.line if diag.line is not None else -1,
                diag.function or "",
                diag.tool,
                diag.code or "-",
                diag.message,
            )
            for diag in diagnostics
        ],
        builder.annotation_engine,
    )
    types_entry = next(entry for entry in advice_entries if entry.category == "Types")
    body = types_entry.body
    for idx in range(5):
        assert f"src/pkg/module{idx}.py" in body
    assert "(+1 more" in body

    magic_entry = next(entry for entry in advice_entries if entry.category == "Constants")
    body_magic = magic_entry.body
    for idx in range(5):
        assert f"src/pkg/config{idx}.py" in body_magic
    assert "(+1 more" in body_magic


def test_render_advice_panel_covers_runtime_and_tests(tmp_path: Path, capsys) -> None:
    diagnostics = [
        _advice_diag(
            file="src/pkg/runtime.py",
            tool="ruff",
            code="T201",
            message="T201 print detected",
        ),
        _advice_diag(
            file="src/pkg/runtime.py",
            tool="ruff",
            code="S101",
            message="S101 assert used",
        ),
        _advice_diag(
            file="src/pkg/service.py",
            tool="ruff",
            code="C901",
            message="C901 complexity",
            function="handle_service",
        ),
        _advice_diag(
            file="src/pkg/hooks.py",
            tool="pylint",
            code="R0915",
            message="R0915 complexity",
            function="perform_hooks",
        ),
        _advice_diag(
            file="src/pkg/duplicate.py",
            tool="ruff",
            code="SIM101",
            message="SIM101 Multiple isinstance calls",
        ),
        _advice_diag(
            file="stubs/pkg.pyi",
            tool="ruff",
            code="ANN401",
            message="ANN401 Missing type annotation",
        ),
        _advice_diag(
            file="src/pkg/impl.py",
            tool="pyright",
            code="reportIncompatibleMethodOverride",
            message="Method override incompatible",
        ),
    ]
    diagnostics.extend(
        _advice_diag(
            file="tests/test_example.py",
            tool="ruff",
            code=f"TST{i}",
            message="Generic test warning",
        )
        for i in range(5)
    )
    outcome = ToolOutcome(
        tool="composite",
        action="lint",
        returncode=1,
        stdout="",
        stderr="",
        diagnostics=diagnostics,
    )
    result = RunResult(
        root=tmp_path,
        files=[tmp_path / "src" / "pkg" / "runtime.py"],
        outcomes=[outcome],
        tool_versions={},
    )
    result.analysis["refactor_navigator"] = [
        {
            "file": "src/pkg/service.py",
            "function": "handle_service",
            "issue_tags": {"complexity": 2, "typing": 1},
            "size": 50,
            "complexity": 9,
        },
    ]
    config = OutputConfig(color=False, emoji=False, advice=True, show_stats=False)
    render(result, config)
    output = capsys.readouterr().out
    assert "Logging: replace debugging prints" in output
    assert "Runtime safety: swap bare assert" in output
    assert "SOLID: DRY up duplicate code" in output
    assert "Test hygiene: refactor noisy tests" in output
    assert "Typing: align stubs with implementations" in output
    assert "Refactor priority: focus on" in output
    assert "handle_service" in output
    assert "perform_hooks" in output
    assert "Refactor Navigator" in output


def test_advice_builder_delegates_to_generate_advice() -> None:
    entries = [
        (
            "src/sample.py",
            4,
            "example",
            "ruff",
            "ANN001",
            "Missing type annotation for function argument foo",
        ),
    ]

    class DummyAnnotationEngine:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def message_spans(self, message: str) -> tuple[MessageSpan, ...]:
            self.calls.append(message)
            return ()

    dummy = DummyAnnotationEngine()
    engine = cast("AnnotationEngine", dummy)
    builder = AdviceBuilder(annotation_engine=engine)

    expected = generate_advice(entries, engine)
    result = builder.build(entries)

    assert result == expected
    assert dummy.calls


def test_duplicate_code_advice_highlights_paths() -> None:
    builder = AdviceBuilder()
    advice_entries = generate_advice(
        [
            (
                "src/pkg/a.py",
                1,
                "",
                "pylint",
                "R0801",
                "Similar lines in 2 files (src/pkg/a.py:[1:6]; src/pkg/b.py:[1:6])",
            ),
        ],
        builder.annotation_engine,
    )
    duplicate_entry = next(entry for entry in advice_entries if entry.category == AdviceCategory.SOLID)
    body = duplicate_entry.body
    assert "DRY" in body
    assert "src/pkg/a.py" in body
    assert "src/pkg/b.py" in body


def test_render_advice_includes_duplicate_clusters(tmp_path: Path, capsys) -> None:
    diagnostics = [
        _advice_diag(
            file="src/pkg/a.py",
            tool="ruff",
            code="E001",
            message="Example warning",
        ),
    ]
    outcome = ToolOutcome(
        tool="ruff",
        action="lint",
        returncode=1,
        stdout="",
        stderr="",
        diagnostics=diagnostics,
    )
    result = RunResult(
        root=tmp_path,
        files=[tmp_path / "src" / "pkg" / "a.py"],
        outcomes=[outcome],
        tool_versions={},
    )
    result.analysis["duplicate_clusters"] = [
        {
            "kind": "ast",
            "fingerprint": "deadbeef",
            "summary": "Duplicate block (~5 lines) detected across 2 locations",
            "occurrences": [
                {"file": "src/pkg/a.py", "line": 10, "function": "alpha", "size": 5, "snippet": None},
                {"file": "src/pkg/b.py", "line": 12, "function": "beta", "size": 5, "snippet": None},
            ],
        },
    ]
    config = OutputConfig(color=False, emoji=False, advice=True)
    render(result, config)
    output = capsys.readouterr().out
    assert "SOLID: DRY up duplicate code" in output
    assert "src/pkg/a.py" in output
    assert "src/pkg/b.py" in output
