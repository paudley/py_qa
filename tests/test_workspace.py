# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Unit tests for workspace helpers."""

from __future__ import annotations

from pathlib import Path

from pyqa.platform.workspace import is_pyqa_lint_workspace


def test_is_pyqa_lint_workspace_true(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "pyqa_lint"\n', encoding="utf-8")
    (tmp_path / "src" / "pyqa").mkdir(parents=True)
    (tmp_path / "src" / "pyqa" / "__init__.py").write_text("""""" "\n", encoding="utf-8")
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (tmp_path / "tooling").mkdir()
    (docs_dir / "ARCHITECTURE.md").write_text("# architecture\n", encoding="utf-8")

    assert is_pyqa_lint_workspace(tmp_path) is True


def test_is_pyqa_lint_workspace_requires_exact_name(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "pyqa"\n', encoding="utf-8")
    (tmp_path / "src" / "pyqa").mkdir(parents=True)
    (tmp_path / "src" / "pyqa" / "__init__.py").write_text("""""" "\n", encoding="utf-8")
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (tmp_path / "tooling").mkdir()
    (docs_dir / "ARCHITECTURE.md").write_text("# architecture\n", encoding="utf-8")

    assert is_pyqa_lint_workspace(tmp_path) is False


def test_is_pyqa_lint_workspace_false(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "other"\n', encoding="utf-8")

    assert is_pyqa_lint_workspace(tmp_path) is False
