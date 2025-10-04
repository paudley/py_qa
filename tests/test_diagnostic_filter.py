# SPDX-License-Identifier: MIT
"""Tests for duplicate-code diagnostic filtering."""

from __future__ import annotations

from pathlib import Path

from pyqa.execution.diagnostic_filter import DuplicateCodeDeduper, filter_diagnostics
from pyqa.models import Diagnostic
from pyqa.severity import Severity


def _build_duplicate_message(entries: list[str]) -> str:
    header = f"Similar lines in {len(entries)} files"
    body = [f"=={entry}" for entry in entries]
    return "\n".join([header, *body, "    sample"])


def test_duplicate_code_suppresses_init_only(tmp_path: Path) -> None:
    pkg_init = tmp_path / "pkg" / "__init__.py"
    other_init = tmp_path / "other" / "__init__.py"
    pkg_init.parent.mkdir(parents=True, exist_ok=True)
    other_init.parent.mkdir(parents=True, exist_ok=True)
    pkg_init.write_text("def foo():\n    return 1\n", encoding="utf-8")
    other_init.write_text("def bar():\n    return 2\n", encoding="utf-8")

    message = _build_duplicate_message([
        "pkg/__init__.py:[1:2]",
        "other/__init__.py:[1:2]",
    ])

    diagnostic = Diagnostic(
        file="pkg/__init__.py",
        line=1,
        column=None,
        severity=Severity.WARNING,
        message=message,
        tool="pylint",
        code="R0801",
    )

    deduper = DuplicateCodeDeduper(tmp_path)
    assert deduper.keep(diagnostic) is False


def test_duplicate_code_suppresses_when_init_in_group(tmp_path: Path) -> None:
    pkg_dir = tmp_path / "pkg"
    pkg_dir.mkdir(parents=True, exist_ok=True)
    (pkg_dir / "__init__.py").write_text("def init():\n    return 1\n", encoding="utf-8")
    (pkg_dir / "module.py").write_text("def init():\n    return 1\n", encoding="utf-8")

    message = _build_duplicate_message([
        "pkg/__init__.py:[1:2]",
        "pkg/module.py:[1:2]",
    ])

    diagnostic = Diagnostic(
        file="pkg/__init__.py",
        line=1,
        column=None,
        severity=Severity.WARNING,
        message=message,
        tool="pylint",
        code="R0801",
    )

    deduper = DuplicateCodeDeduper(tmp_path)
    assert deduper.keep(diagnostic) is False


def test_tombi_suppresses_out_of_order_tables(tmp_path: Path) -> None:
    message = "Defining tables out-of-order is discouraged (table \"tool\")"
    diagnostic = Diagnostic(
        file="pyproject.toml",
        line=5,
        column=None,
        severity=Severity.WARNING,
        message=message,
        tool="tombi",
        code=None,
    )

    filtered = filter_diagnostics([diagnostic], "tombi", [], tmp_path)
    assert filtered == []


def test_tombi_retains_out_of_order_warning_for_other_files(tmp_path: Path) -> None:
    message = "Defining tables out-of-order is discouraged"
    diagnostic = Diagnostic(
        file="tool.toml",
        line=5,
        column=None,
        severity=Severity.WARNING,
        message=message,
        tool="tombi",
        code=None,
    )

    filtered = filter_diagnostics([diagnostic], "tombi", [], tmp_path)
    assert filtered == [diagnostic]
