# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Tests for the sparkly-clean utility."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from pyqa.clean import sparkly_clean
from pyqa.cli.app import app
from pyqa.config import CleanConfig


def _setup_repo(root: Path) -> None:
    (root / "build").mkdir()
    (root / "build" / "__pycache__").mkdir()
    (root / "build" / "__pycache__" / "cache.pyc").write_text("cache", encoding="utf-8")
    (root / "coverage.xml").write_text("<coverage/>", encoding="utf-8")
    (root / "examples").mkdir()
    (root / "examples" / "test.log").write_text("log", encoding="utf-8")


def test_sparkly_clean_removes_known_patterns(tmp_path: Path) -> None:
    _setup_repo(tmp_path)
    sparkly_clean(tmp_path, config=CleanConfig(), dry_run=False)
    assert not (tmp_path / "coverage.xml").exists()
    assert not (tmp_path / "examples" / "test.log").exists()
    assert not any((tmp_path / "build").rglob("__pycache__"))


def test_cli_dry_run_lists_paths(tmp_path: Path) -> None:
    _setup_repo(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "sparkly-clean",
            "--root",
            str(tmp_path),
            "--dry-run",
            "--no-emoji",
        ],
    )
    assert result.exit_code == 0
    assert "DRY RUN" in result.stdout
