# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""CLI tests for configuration commands."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from pyqa.cli.app import app


def test_config_show_outputs_json(tmp_path: Path, monkeypatch) -> None:
    runner = CliRunner()

    project_root = tmp_path / "project"
    project_root.mkdir()

    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")

    (project_root / ".pyqa_lint.toml").write_text(
        """
[execution]
jobs = 3

[tools.black]
line-length = 88
""".strip(),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["config", "show", "--root", str(project_root), "--no-trace"])

    assert result.exit_code == 0
    stdout = result.stdout.split("\n\n# Warnings", 1)[0]
    payload = json.loads(stdout)
    assert payload["execution"]["jobs"] == 3
    assert payload["execution"]["line_length"] == 120
    assert payload["execution"]["sql_dialect"] == "postgres"
    assert payload["tool_settings"]["black"]["line-length"] == 88


def test_config_validate_failure(tmp_path: Path, monkeypatch) -> None:
    runner = CliRunner()

    project_root = tmp_path / "project"
    project_root.mkdir()

    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")

    (project_root / ".pyqa_lint.toml").write_text(
        """
severity_rules = 42
""".strip(),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["config", "validate", "--root", str(project_root)])

    assert result.exit_code != 0
    assert "invalid" in result.stdout.lower()


def test_config_schema_markdown(tmp_path: Path, monkeypatch) -> None:
    runner = CliRunner()

    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")

    result = runner.invoke(app, ["config", "schema", "--format", "markdown"])

    assert result.exit_code == 0
    assert "## file_discovery" in result.stdout
    assert "| roots |" in result.stdout
    assert "## tool_settings" in result.stdout


def test_config_schema_json_tools(tmp_path: Path, monkeypatch) -> None:
    runner = CliRunner()

    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")

    result = runner.invoke(app, ["config", "schema", "--format", "json-tools"])

    assert result.exit_code == 0
    assert '"ruff"' in result.stdout
    assert '"black"' in result.stdout


def test_config_schema_json_tools_to_file(tmp_path: Path, monkeypatch) -> None:
    runner = CliRunner()

    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")

    out_path = tmp_path / "schema" / "tools.json"
    result = runner.invoke(
        app,
        [
            "config",
            "schema",
            "--format",
            "json-tools",
            "--out",
            str(out_path),
        ],
    )

    assert result.exit_code == 0
    assert str(out_path.resolve()) in result.stdout
    content = out_path.read_text(encoding="utf-8")
    assert '"ruff"' in content


def test_config_show_trace_includes_descriptions(tmp_path: Path, monkeypatch) -> None:
    runner = CliRunner()

    project_root = tmp_path / "project"
    project_root.mkdir()

    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")

    (project_root / ".pyqa_lint.toml").write_text(
        """
[tools.black]
line-length = 90
""".strip(),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["config", "show", "--root", str(project_root), "--trace"])

    assert result.exit_code == 0
    assert "tool_settings.black" in result.stdout
    assert "line-length" in result.stdout
    assert "Maximum line length enforced by Black" in result.stdout


def test_config_show_warns_on_unknown_setting(tmp_path: Path, monkeypatch) -> None:
    runner = CliRunner()

    project_root = tmp_path / "project"
    project_root.mkdir()

    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")

    (project_root / ".pyqa_lint.toml").write_text(
        """
[tools.black]
unknown = true
""".strip(),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["config", "show", "--root", str(project_root)])

    assert result.exit_code == 0
    assert "# Warnings" in result.stdout
    assert "Unknown option 'unknown'" in result.stdout


def test_config_show_strict_errors_on_unknown(tmp_path: Path, monkeypatch) -> None:
    runner = CliRunner()

    project_root = tmp_path / "project"
    project_root.mkdir()

    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")

    (project_root / ".pyqa_lint.toml").write_text(
        """
[tools.black]
unknown = true
""".strip(),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["config", "show", "--root", str(project_root), "--strict"])

    assert result.exit_code != 0
    assert "Unknown option 'unknown'" in result.stdout


def test_config_diff_defaults_to_final(tmp_path: Path, monkeypatch) -> None:
    runner = CliRunner()
    project_root = tmp_path / "project"
    project_root.mkdir()
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")

    (project_root / ".pyqa_lint.toml").write_text(
        """
[execution]
jobs = 8
""".strip(),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["config", "diff", "--root", str(project_root)])

    assert result.exit_code == 0
    assert '"execution.jobs"' in result.stdout


def test_config_diff_to_file(tmp_path: Path, monkeypatch) -> None:
    runner = CliRunner()
    project_root = tmp_path / "project"
    project_root.mkdir()
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")

    (project_root / ".pyqa_lint.toml").write_text(
        """
[tools.black]
line-length = 99
""".strip(),
        encoding="utf-8",
    )

    out_path = project_root / "diff.json"
    result = runner.invoke(
        app,
        [
            "config",
            "diff",
            "--root",
            str(project_root),
            "--out",
            str(out_path),
        ],
    )

    assert result.exit_code == 0
    assert out_path.exists()
    written = out_path.read_text(encoding="utf-8")
    assert '"tool_settings.black.line-length"' in written


def test_config_export_tools(tmp_path: Path, monkeypatch) -> None:
    runner = CliRunner()
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")

    out_path = tmp_path / "tool-schema.json"
    result = runner.invoke(app, ["config", "export-tools", str(out_path)])

    assert result.exit_code == 0
    assert out_path.exists()
    content = json.loads(out_path.read_text(encoding="utf-8"))
    assert "ruff" in content
