# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Tests for the security scan CLI command."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from pyqa.cli.app import app


def test_security_scan_detects_secret(tmp_path: Path) -> None:
    runner = CliRunner()
    secret_file = tmp_path / "secret.txt"
    secret_file.write_text('api_key = "ABCDEFGHIJKLMNOPQRSTUV"\n', encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "security-scan",
            str(secret_file),
            "--root",
            str(tmp_path),
            "--no-bandit",
            "--no-staged",
            "--no-emoji",
        ],
    )

    assert result.exit_code == 1
    assert "api_key" in result.stdout


def test_security_scan_respects_excludes(tmp_path: Path) -> None:
    runner = CliRunner()
    secret_file = tmp_path / "secret.txt"
    secret_file.write_text('api_key = "ABCDEFGHIJKLMNOPQRSTUV"\n', encoding="utf-8")
    (tmp_path / ".security-check-excludes").write_text("secret.txt\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "security-scan",
            str(secret_file),
            "--root",
            str(tmp_path),
            "--no-bandit",
            "--no-staged",
            "--no-emoji",
        ],
    )

    assert result.exit_code == 0
    assert "No security issues detected" in result.stdout


def test_security_scan_handles_no_files(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "security-scan",
            "--root",
            str(tmp_path),
            "--no-bandit",
            "--no-staged",
            "--no-emoji",
        ],
    )

    assert result.exit_code == 0
    assert "No files to scan" in result.stdout
