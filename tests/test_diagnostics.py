# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Tests for diagnostic normalization and deduplication."""

# pylint: disable=missing-function-docstring

from pathlib import Path

from pyqa.config import DedupeConfig
from pyqa.diagnostics import (
    build_severity_rules,
    dedupe_outcomes,
    normalize_diagnostics,
)
from pyqa.models import Diagnostic, RawDiagnostic, RunResult, ToolOutcome
from pyqa.severity import Severity


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
            ToolOutcome("ruff", "lint", 1, "", "", diagnostics=[diag_warn]),
            ToolOutcome("pylint", "lint", 1, "", "", diagnostics=[diag_error]),
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
            ToolOutcome("ruff", "lint", 1, "", "", diagnostics=[diag_a]),
            ToolOutcome("pylint", "lint", 1, "", "", diagnostics=[diag_b]),
        ],
    )

    dedupe_outcomes(result, cfg)

    assert len(result.outcomes[0].diagnostics) == 0
    assert result.outcomes[1].diagnostics == [diag_b]
