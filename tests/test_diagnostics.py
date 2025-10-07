# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Tests for diagnostic normalization and deduplication."""

from pathlib import Path

from pyqa.config import DedupeConfig
from pyqa.core.models import Diagnostic, RawDiagnostic, RunResult, ToolOutcome
from pyqa.core.severity import Severity
from pyqa.diagnostics import (
    build_severity_rules,
    dedupe_outcomes,
    normalize_diagnostics,
)


def test_normalize_diagnostics_applies_rules() -> None:
    raw = RawDiagnostic(
        file="src/app.py",
        line=1,
        column=1,
        severity="warning",
        message="invalid name",
        code="C0103",
        tool="pylint",
    )
    rules = build_severity_rules([])

    diags = normalize_diagnostics([raw], tool_name="pylint", severity_rules=rules)

    assert len(diags) == 1
    diag = diags[0]
    assert diag.severity == Severity.NOTICE  # mapped via default rule
    assert diag.message.startswith("C0103")
    assert diag.tool == "pylint"


def test_dedupe_prefers_higher_severity(tmp_path: Path) -> None:
    cfg = DedupeConfig(dedupe=True, dedupe_by="severity", dedupe_line_fuzz=0)
    diag_warn = Diagnostic(
        file="src/app.py",
        line=10,
        column=None,
        severity=Severity.WARNING,
        message="something",
        tool="ruff",
        code="W001",
    )
    diag_error = Diagnostic(
        file="src/app.py",
        line=10,
        column=None,
        severity=Severity.ERROR,
        message="something",
        tool="pylint",
        code="W001",
    )

    result = RunResult(
        root=tmp_path,
        files=[tmp_path / "src" / "app.py"],
        outcomes=[
            ToolOutcome(
                tool="ruff",
                action="lint",
                returncode=1,
                stdout="",
                stderr="",
                diagnostics=[diag_warn],
            ),
            ToolOutcome(
                tool="pylint",
                action="lint",
                returncode=1,
                stdout="",
                stderr="",
                diagnostics=[diag_error],
            ),
        ],
    )

    dedupe_outcomes(result, cfg)

    assert len(result.outcomes[0].diagnostics) == 0
    assert result.outcomes[1].diagnostics == [diag_error]


def test_dedupe_prefer_list(tmp_path: Path) -> None:
    cfg = DedupeConfig(
        dedupe=True,
        dedupe_by="prefer",
        dedupe_prefer=["pylint"],
        dedupe_line_fuzz=1,
    )
    diag_a = Diagnostic(
        file="src/app.py",
        line=20,
        column=None,
        severity=Severity.WARNING,
        message="issue",
        tool="ruff",
        code="W100",
    )
    diag_b = Diagnostic(
        file="src/app.py",
        line=21,
        column=None,
        severity=Severity.WARNING,
        message="issue",
        tool="pylint",
        code="W100",
    )

    result = RunResult(
        root=tmp_path,
        files=[tmp_path / "src" / "app.py"],
        outcomes=[
            ToolOutcome(
                tool="ruff",
                action="lint",
                returncode=1,
                stdout="",
                stderr="",
                diagnostics=[diag_a],
            ),
            ToolOutcome(
                tool="pylint",
                action="lint",
                returncode=1,
                stdout="",
                stderr="",
                diagnostics=[diag_b],
            ),
        ],
    )

    dedupe_outcomes(result, cfg)

    assert len(result.outcomes[0].diagnostics) == 0
    assert result.outcomes[1].diagnostics == [diag_b]


def test_dedupe_prefers_pyright_over_mypy(tmp_path: Path) -> None:
    cfg = DedupeConfig(
        dedupe=True,
        dedupe_by="prefer",
        dedupe_prefer=["pyright", "mypy"],
        dedupe_line_fuzz=0,
    )
    diag_mypy = Diagnostic(
        file="tests/test_reporting.py",
        line=1126,
        column=None,
        severity=Severity.WARNING,
        message='Argument "stdout" to "ToolOutcome" has incompatible type "str"; expected "list[str]"',
        tool="mypy",
        code="arg-type",
    )
    diag_pyright = Diagnostic(
        file="tests/test_reporting.py",
        line=1126,
        column=None,
        severity=Severity.WARNING,
        message='Argument of type "Literal[\'\']" cannot be assigned to parameter "stdout" of type "list[str]" in function "__init__"',
        tool="pyright",
        code="reportArgumentType",
    )

    result = RunResult(
        root=tmp_path,
        files=[tmp_path / "tests" / "test_reporting.py"],
        outcomes=[
            ToolOutcome(
                tool="mypy",
                action="lint",
                returncode=1,
                stdout=[],
                stderr=[],
                diagnostics=[diag_mypy],
            ),
            ToolOutcome(
                tool="pyright",
                action="lint",
                returncode=1,
                stdout=[],
                stderr=[],
                diagnostics=[diag_pyright],
            ),
        ],
    )

    dedupe_outcomes(result, cfg)

    assert not result.outcomes[0].diagnostics
    assert result.outcomes[1].diagnostics == [diag_pyright]


def test_dedupe_cross_tool_undefined_variable(tmp_path: Path) -> None:
    cfg = DedupeConfig(dedupe=True, dedupe_line_fuzz=0)
    diag_pyright = Diagnostic(
        file="src/pyqa/parsers/misc.py",
        line=275,
        column=None,
        severity=Severity.ERROR,
        message='"map_severity" is not defined',
        tool="pyright",
        code="reportUndefinedVariable",
    )
    diag_pylint = Diagnostic(
        file="src/pyqa/parsers/misc.py",
        line=275,
        column=None,
        severity=Severity.ERROR,
        message="Undefined variable 'map_severity'",
        tool="pylint",
        code="undefined-variable",
    )
    diag_ruff = Diagnostic(
        file="src/pyqa/parsers/misc.py",
        line=275,
        column=None,
        severity=Severity.ERROR,
        message="Undefined name map_severity",
        tool="ruff",
        code="F821",
    )

    result = RunResult(
        root=tmp_path,
        files=[tmp_path / "src" / "pyqa" / "parsers" / "misc.py"],
        outcomes=[
            ToolOutcome(
                tool="pyright",
                action="lint",
                returncode=1,
                stdout="",
                stderr="",
                diagnostics=[diag_pyright],
            ),
            ToolOutcome(
                tool="pylint",
                action="lint",
                returncode=1,
                stdout="",
                stderr="",
                diagnostics=[diag_pylint],
            ),
            ToolOutcome(
                tool="ruff",
                action="lint",
                returncode=1,
                stdout="",
                stderr="",
                diagnostics=[diag_ruff],
            ),
        ],
    )

    dedupe_outcomes(result, cfg)

    assert result.outcomes[0].diagnostics == [diag_pyright]
    assert not result.outcomes[1].diagnostics
    assert not result.outcomes[2].diagnostics
