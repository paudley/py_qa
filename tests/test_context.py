"""Tests for structural context extraction."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

try:
    from tree_sitter import Parser  # type: ignore[attr-defined]
except ModuleNotFoundError:  # pragma: no cover
    Parser = None  # type: ignore[assignment]

from pyqa.context import TreeSitterContextResolver
from pyqa.models import Diagnostic
from pyqa.severity import Severity

pytestmark = pytest.mark.skipif(Parser is None, reason="tree-sitter not available")


def test_python_context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = textwrap.dedent(
        """
        def outer():
            def inner():
                return 1
            return inner()
        """
    ).strip()
    file_path = tmp_path / "sample.py"
    file_path.write_text(source, encoding="utf-8")

    diag = Diagnostic(
        file=str(file_path),
        line=3,
        column=None,
        severity=Severity.ERROR,
        message="",
        tool="ruff",
    )

    resolver = TreeSitterContextResolver()

    def fail_fallback(path: Path, line: int) -> str:
        raise AssertionError("fallback should not be used")

    monkeypatch.setattr(TreeSitterContextResolver, "_python_fallback", staticmethod(fail_fallback))

    resolver.annotate([diag], root=tmp_path)

    assert diag.function == "inner"
    assert resolver._disabled == set()


def test_markdown_context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = textwrap.dedent(
        """
        # Title

        Some intro

        ## Section

        Content line
        """
    ).strip()
    file_path = tmp_path / "doc.md"
    file_path.write_text(source, encoding="utf-8")

    diag = Diagnostic(
        file=str(file_path),
        line=6,
        column=None,
        severity=Severity.ERROR,
        message="",
        tool="markdownlint",
    )

    resolver = TreeSitterContextResolver()

    def fail_fallback(path: Path, line: int) -> str:
        raise AssertionError("fallback should not be used")

    monkeypatch.setattr(
        TreeSitterContextResolver,
        "_markdown_fallback",
        staticmethod(fail_fallback),
    )

    resolver.annotate([diag], root=tmp_path)

    assert diag.function == "Section"
