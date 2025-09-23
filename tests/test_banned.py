# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Tests for the banned word checker and CLI."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from pyqa.banned import BannedWordChecker
from pyqa.cli.app import app


def test_checker_detects_terms(tmp_path: Path) -> None:
    checker = BannedWordChecker(root=tmp_path)
    matches = checker.scan(["This contains password123 in the text"])
    assert "password123" in matches


def test_checker_respects_repo_list(tmp_path: Path) -> None:
    (tmp_path / ".banned-words").write_text("custom-term\n", encoding="utf-8")
    checker = BannedWordChecker(root=tmp_path)
    matches = checker.scan(["message mentioning custom-term here"])
    assert "custom-term" in matches


def test_check_banned_words_cli(tmp_path: Path) -> None:
    runner = CliRunner()
    commit_msg = tmp_path / "commit.txt"
    commit_msg.write_text("This is a quick hack.\n", encoding="utf-8")

    result = runner.invoke(
        app, ["check-banned-words", str(commit_msg), "--root", str(tmp_path)]
    )

    assert result.exit_code == 1
    assert "quick hack" in result.stdout


def test_check_banned_words_cli_ok(tmp_path: Path) -> None:
    runner = CliRunner()
    commit_msg = tmp_path / "commit.txt"
    commit_msg.write_text("Normal update message\n", encoding="utf-8")

    result = runner.invoke(
        app, ["check-banned-words", str(commit_msg), "--root", str(tmp_path)]
    )

    assert result.exit_code == 0
    assert "No banned words" in result.stdout
