# SPDX-License-Identifier: MIT
"""Tests for duplicate code detection heuristics."""

from __future__ import annotations

from pathlib import Path

from pyqa.analysis.duplication import detect_duplicate_code
from pyqa.config import DuplicateDetectionConfig
from pyqa.models import Diagnostic, RunResult, Severity, ToolOutcome


def _outcome_with_diagnostics(*diagnostics: Diagnostic) -> ToolOutcome:
    return ToolOutcome(
        tool="synthetic",
        action="lint",
        returncode=1,
        stdout="",
        stderr="",
        diagnostics=list(diagnostics),
    )


def test_detect_duplicate_code_ast(tmp_path: Path) -> None:
    file_a = tmp_path / "a.py"
    file_b = tmp_path / "b.py"
    file_a.write_text(
        """
        def foo():
            total = 0
            for value in range(5):
                total += value
            return total
        """.strip()
        + "\n",
        encoding="utf-8",
    )
    file_b.write_text(
        """
        def bar():
            total = 0
            for value in range(5):
                total += value
            return total
        """.strip()
        + "\n",
        encoding="utf-8",
    )
    result = RunResult(
        root=tmp_path,
        files=[file_a, file_b],
        outcomes=[_outcome_with_diagnostics()],
        tool_versions={},
    )
    config = DuplicateDetectionConfig(
        ast_min_lines=3,
        ast_min_nodes=1,
        cross_diagnostics=False,
    )

    clusters = detect_duplicate_code(result, config)

    assert clusters
    ast_clusters = [cluster for cluster in clusters if cluster.get("kind") == "ast"]
    assert ast_clusters
    occurrences = ast_clusters[0]["occurrences"]
    assert len(occurrences) == 2


def test_detect_duplicate_code_cross_diagnostics(tmp_path: Path) -> None:
    diag1 = Diagnostic(
        file="src/pkg/a.py",
        line=4,
        column=None,
        severity=Severity.WARNING,
        message="Shared warning",
        tool="ruff",
        code="X001",
    )
    diag2 = diag1.model_copy(update={"file": "src/pkg/b.py", "line": 8})
    result = RunResult(
        root=tmp_path,
        files=[tmp_path / "src" / "pkg" / "a.py", tmp_path / "src" / "pkg" / "b.py"],
        outcomes=[_outcome_with_diagnostics(diag1, diag2)],
        tool_versions={},
    )
    config = DuplicateDetectionConfig(
        ast_enabled=False,
        cross_diagnostics=True,
        cross_message_threshold=2,
    )

    clusters = detect_duplicate_code(result, config)

    diag_clusters = [cluster for cluster in clusters if cluster.get("kind") == "diagnostic"]
    assert diag_clusters
    assert len(diag_clusters[0]["occurrences"]) == 2


def test_detect_duplicate_code_disabled(tmp_path: Path) -> None:
    result = RunResult(
        root=tmp_path,
        files=[],
        outcomes=[_outcome_with_diagnostics()],
        tool_versions={},
    )
    config = DuplicateDetectionConfig(enabled=False)

    assert detect_duplicate_code(result, config) == []
