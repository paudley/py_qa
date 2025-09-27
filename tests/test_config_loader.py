# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Tests for layered configuration loading."""

from __future__ import annotations

from pathlib import Path

import pytest

from pyqa.config import ConfigError
from pyqa.config_loader import ConfigLoader, generate_config_schema, load_config


def test_load_config_defaults(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    project_root = tmp_path / "project"
    project_root.mkdir()

    monkeypatch.setattr(Path, "home", lambda: home_dir)

    cfg = load_config(project_root)

    assert cfg.file_discovery.roots == [project_root.resolve()]
    assert cfg.execution.cache_dir == (project_root / ".lint-cache").resolve()
    assert cfg.execution.line_length == 120
    assert cfg.execution.sql_dialect == "postgresql"
    assert cfg.output.pr_summary_out is None


def test_config_loader_merges_user_and_project(tmp_path: Path) -> None:
    project_root = tmp_path / "workspace"
    project_root.mkdir()

    user_config = tmp_path / "user.toml"
    user_config.write_text(
        """
[file_discovery]
excludes = ["build", "dist"]

[execution]
jobs = 5

[output]
verbose = true
pr_summary_out = "reports/user.md"
""".strip(),
        encoding="utf-8",
    )

    project_config = project_root / ".py_qa.toml"
    project_config.write_text(
        """
[file_discovery]
excludes = ["node_modules"]

[execution]
jobs = 9

[output]
verbose = false
sarif_out = "reports/result.sarif"
""".strip(),
        encoding="utf-8",
    )

    loader = ConfigLoader.for_root(
        project_root,
        user_config=user_config,
        project_config=project_config,
    )

    cfg = loader.load()

    excludes = {path.resolve() for path in cfg.file_discovery.excludes}
    assert (project_root / "build").resolve() in excludes
    assert (project_root / "dist").resolve() in excludes
    assert (project_root / "node_modules").resolve() in excludes

    assert cfg.execution.jobs == 9

    assert not cfg.output.verbose
    assert cfg.output.sarif_out == (project_root / "reports/result.sarif").resolve()
    assert cfg.output.pr_summary_out == (project_root / "reports/user.md").resolve()


def test_config_loader_invalid_severity(tmp_path: Path) -> None:
    project_root = tmp_path / "workspace"
    project_root.mkdir()

    project_config = project_root / ".py_qa.toml"
    project_config.write_text(
        """
severity_rules = "oops"
""".strip(),
        encoding="utf-8",
    )

    loader = ConfigLoader.for_root(
        project_root,
        user_config=tmp_path / "missing.toml",
        project_config=project_config,
    )

    with pytest.raises(ConfigError):
        loader.load()


def test_config_loader_supports_includes(tmp_path: Path) -> None:
    project_root = tmp_path / "workspace"
    project_root.mkdir()

    inner = project_root / "inner.toml"
    inner.write_text(
        """
[execution]
jobs = 4
cache_enabled = false
""".strip(),
        encoding="utf-8",
    )

    project_config = project_root / ".py_qa.toml"
    project_config.write_text(
        f"""
include = ["{inner.name}"]

[file_discovery]
excludes = ["build"]

[output]
report_out = "reports/output.json"
""".strip(),
        encoding="utf-8",
    )

    loader = ConfigLoader.for_root(project_root, project_config=project_config)
    cfg = loader.load()

    assert cfg.execution.jobs == 4
    assert not cfg.execution.cache_enabled
    assert (project_root / "build").resolve() in {
        path.resolve() for path in cfg.file_discovery.excludes
    }
    assert cfg.output.report_out == (project_root / "reports/output.json").resolve()


def test_config_loader_expands_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project_root = tmp_path / "workspace"
    project_root.mkdir()

    monkeypatch.setenv("REPORT_DIR", str(project_root / "artifacts"))

    project_config = project_root / ".py_qa.toml"
    project_config.write_text(
        """
[output]
pr_summary_out = "${REPORT_DIR}/summary.md"
""".strip(),
        encoding="utf-8",
    )

    cfg = ConfigLoader.for_root(project_root).load()

    assert cfg.output.pr_summary_out == (project_root / "artifacts/summary.md").resolve()


def test_pyproject_tool_section_is_loaded(tmp_path: Path) -> None:
    project_root = tmp_path / "workspace"
    project_root.mkdir()

    pyproject = project_root / "pyproject.toml"
    pyproject.write_text(
        """
[tool.pyqa.output]
quiet = true

[tool.pyqa.execution]
jobs = 7
""".strip(),
        encoding="utf-8",
    )

    cfg = ConfigLoader.for_root(project_root).load()

    assert cfg.output.quiet
    assert cfg.execution.jobs == 7


def test_load_with_trace_reports_sources(tmp_path: Path) -> None:
    project_root = tmp_path / "workspace"
    project_root.mkdir()

    project_config = project_root / ".py_qa.toml"
    project_config.write_text(
        """
[execution]
jobs = 11
""".strip(),
        encoding="utf-8",
    )

    result = ConfigLoader.for_root(project_root, project_config=project_config).load_with_trace()

    assert result.config.execution.jobs == 11
    assert result.config.execution.line_length == 120

    sources = {update.source for update in result.updates if update.field == "jobs"}
    assert str(project_config) in sources


def test_generate_config_schema_exposes_defaults() -> None:
    schema = generate_config_schema()

    assert "file_discovery" in schema
    assert schema["file_discovery"]["roots"]["default"] == ["."]
    assert schema["output"]["emoji"]["default"] is True
    defaults = schema["tool_settings"]["default"]
    assert defaults["black"]["line-length"] == 120
    assert defaults["isort"]["line-length"] == 120
    assert defaults["luacheck"]["max-cyclomatic-complexity"] == 10
    assert defaults["mypy"]["strict"] is True
    assert defaults["mypy"]["show-error-codes"] is True
    assert defaults["tsc"]["strict"] is True
    tools_schema = schema["tool_settings"]["tools"]
    assert "max-complexity" in tools_schema["pylint"]
    assert "max-args" in tools_schema["pylint"]
    assert "max-cyclomatic-complexity" in tools_schema["luacheck"]
    assert schema["complexity"]["max_complexity"]["default"] == 10
    assert schema["strictness"]["type_checking"]["default"] == "strict"
    assert schema["execution"]["line_length"]["default"] == 120
    assert schema["severity"]["bandit_level"]["default"] == "medium"
    assert schema["severity"]["pylint_fail_under"]["default"] == 9.5
    assert "tools" in schema["tool_settings"]
    assert "ruff" in schema["tool_settings"]["tools"]


def test_tool_settings_warnings(tmp_path: Path) -> None:
    project_root = tmp_path / "workspace"
    project_root.mkdir()

    config_file = project_root / ".py_qa.toml"
    config_file.write_text(
        """
[tools.black]
line-length = 88
unknown = true
""".strip(),
        encoding="utf-8",
    )

    loader = ConfigLoader.for_root(project_root, project_config=config_file)
    result = loader.load_with_trace()

    assert any("unknown option" in message.lower() for message in result.warnings)

    with pytest.raises(ConfigError):
        loader.load(strict=True)


def test_tool_settings_merge_precedence(tmp_path: Path) -> None:
    project_root = tmp_path / "workspace"
    project_root.mkdir()

    pyproject = project_root / "pyproject.toml"
    pyproject.write_text(
        """
[tool.pyqa.bandit]
level = "basic"

[tool.pyqa.tools.ruff]
target-version = "py311"
""".strip(),
        encoding="utf-8",
    )

    user_config = tmp_path / "user.toml"
    user_config.write_text(
        """
[tools.bandit]
level = "strict"
ignore = ["S101"]
""".strip(),
        encoding="utf-8",
    )

    project_config = project_root / ".py_qa.toml"
    project_config.write_text(
        """
[ruff]
line-length = 88

[tools.bandit]
ignore = ["S101", "S102"]
""".strip(),
        encoding="utf-8",
    )

    cfg = ConfigLoader.for_root(
        project_root,
        user_config=user_config,
        project_config=project_config,
    ).load()

    assert cfg.tool_settings["bandit"]["level"] == "basic"
    # project adds extra ignore while retaining level from pyproject/user blend
    assert cfg.tool_settings["bandit"]["ignore"] == ["S101", "S102"]
    assert cfg.tool_settings["ruff"]["line-length"] == 88
    assert cfg.tool_settings["ruff"]["target-version"] == "py311"


def test_auto_discover_tool_settings(tmp_path: Path) -> None:
    project_root = tmp_path / "workspace"
    project_root.mkdir()

    (project_root / "ruff.toml").write_text("", encoding="utf-8")

    loader = ConfigLoader.for_root(project_root)
    result = loader.load_with_trace()

    assert result.config.tool_settings["ruff"]["config"] == "ruff.toml"
    assert any(update.source == "auto" for update in result.updates)
