# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Tests for the doctor CLI command."""

from __future__ import annotations

from typer.testing import CliRunner

from pyqa.cli.app import app


def test_doctor_option(monkeypatch) -> None:
    runner = CliRunner()

    def fake_run_doctor(root):
        print(f"doctor invoked for {root}")
        return 0

    monkeypatch.setattr("pyqa.cli.lint.run_doctor", fake_run_doctor)

    result = runner.invoke(app, ["lint", "--doctor"])

    assert result.exit_code == 0
    assert "doctor invoked" in result.stdout
