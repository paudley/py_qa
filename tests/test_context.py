"""Tests for structural context extraction."""

from __future__ import annotations

import textwrap
from pathlib import Path

from pyqa.context import TreeSitterContextResolver
from pyqa.models import Diagnostic
from pyqa.severity import Severity


def test_python_context_fallback(tmp_path: Path) -> None:
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
    resolver.annotate([diag], root=tmp_path)

    assert diag.function == "inner"


def test_markdown_context_fallback(tmp_path: Path) -> None:
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
    resolver.annotate([diag], root=tmp_path)

    assert diag.function == "Section"
