# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Unit tests for workspace helpers."""

from __future__ import annotations

from pathlib import Path

from pyqa.workspace import is_py_qa_workspace


def test_is_py_qa_workspace_true(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "py_qa"\n', encoding="utf-8")

    assert is_py_qa_workspace(tmp_path) is True


def test_is_py_qa_workspace_accepts_variant(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "pyqa"\n', encoding="utf-8")

    assert is_py_qa_workspace(tmp_path) is True


def test_is_py_qa_workspace_false(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "other"\n', encoding="utf-8")

    assert is_py_qa_workspace(tmp_path) is False
