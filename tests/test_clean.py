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


def test_sparkly_clean_skips_pyqa_lint_outside_workspace(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    vendor_pyqa_lint = project_root / "vendor" / "pyqa_lint"
    vendor_pyqa_lint.mkdir(parents=True)
    candidate = vendor_pyqa_lint / ".coverage"
    candidate.write_text("coverage", encoding="utf-8")

    result = sparkly_clean(project_root, config=CleanConfig(), dry_run=False)

    assert candidate.exists()
    assert candidate not in result.removed
    ignored = {str(path.resolve()) for path in result.ignored_pyqa_lint}
    candidate_options = {
        str(candidate.resolve()),
        str(candidate.parent.resolve()),
        str(vendor_pyqa_lint.resolve()),
    }
    assert ignored & candidate_options


def test_cli_warns_about_pyqa_lint_skip(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    project_root.mkdir()
    vendor_pyqa_lint = project_root / "vendor" / "pyqa_lint"
    vendor_pyqa_lint.mkdir(parents=True)
    candidate = vendor_pyqa_lint / "build" / "artefact.log"
    candidate.parent.mkdir(parents=True, exist_ok=True)
    candidate.write_text("data", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "sparkly-clean",
            "--root",
            str(project_root),
            "--no-emoji",
        ],
    )

    assert result.exit_code == 0
    assert "'pyqa_lint' directories are skipped" in result.stdout
    assert candidate.exists()
