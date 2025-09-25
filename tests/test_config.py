# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Tests covering CLI configuration helpers."""

from pathlib import Path

import pytest

from pyqa.cli.config_builder import DEFAULT_TOOL_FILTERS, build_config
from pyqa.cli.options import LintOptions
from pyqa.config import Config


def test_build_config_defaults(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure CLI option translation produces a fully populated config."""
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home_dir)

    options = LintOptions(
        paths=[],
        root=tmp_path,
        changed_only=False,
        diff_ref="HEAD",
        include_untracked=True,
        base_branch=None,
        paths_from_stdin=False,
        dirs=[],
        exclude=[],
        filters=[],
        only=[],
        language=[],
        fix_only=False,
        check_only=False,
        verbose=False,
        quiet=False,
        no_color=False,
        no_emoji=False,
        output_mode="concise",
        show_passing=False,
        jobs=2,
        bail=False,
        no_cache=True,
        cache_dir=tmp_path / ".cache",
        pr_summary_out=None,
        pr_summary_limit=100,
        pr_summary_min_severity="warning",
        pr_summary_template="- {message}",
        use_local_linters=False,
        provided={"jobs", "no_cache", "cache_dir", "pr_summary_template"},
    )

    cfg: Config = build_config(options)

    dump = cfg.model_dump()
    file_cfg = dump["file_discovery"]
    exec_cfg = dump["execution"]
    output_cfg = dump["output"]

    assert file_cfg["roots"] == [tmp_path.resolve()]
    assert file_cfg["diff_ref"] == "HEAD"
    assert not exec_cfg["only"]
    assert not exec_cfg["languages"]
    assert not exec_cfg["fix_only"]
    assert not exec_cfg["check_only"]
    assert exec_cfg["jobs"] == 2
    assert not exec_cfg["cache_enabled"]
    assert exec_cfg["cache_dir"] == tmp_path / ".cache"
    assert not exec_cfg["bail"]
    assert not exec_cfg["use_local_linters"]
    assert output_cfg["pr_summary_limit"] == 100
    assert output_cfg["pr_summary_min_severity"] == "warning"
    assert output_cfg["pr_summary_template"]
    assert not output_cfg["quiet"]
    assert output_cfg["tool_filters"] == DEFAULT_TOOL_FILTERS
    assert output_cfg["output"] == "concise"
    assert output_cfg["color"]
    assert output_cfg["emoji"]
    exclude_names = {path.name for path in file_cfg["excludes"]}
    assert ".lint-cache" in exclude_names
    assert ".cache" in exclude_names
    assert cfg.tool_settings["mypy"]["strict"] is True
    assert cfg.tool_settings["mypy"]["show-error-codes"] is True
    assert cfg.tool_settings["pylint"]["max-complexity"] == 10
    assert cfg.tool_settings["luacheck"]["max-cyclomatic-complexity"] == 10
    assert cfg.tool_settings["bandit"]["severity"] == "medium"
    assert cfg.tool_settings["bandit"]["confidence"] == "medium"
    assert cfg.tool_settings["pylint"]["fail-under"] == 9.5


def test_build_config_cli_overrides_complexity_and_strictness(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home_dir)

    options = LintOptions(
        paths=[],
        root=tmp_path,
        changed_only=False,
        diff_ref="HEAD",
        include_untracked=True,
        base_branch=None,
        paths_from_stdin=False,
        max_complexity=7,
        max_arguments=4,
        type_checking="lenient",
        bandit_severity="high",
        bandit_confidence="low",
        pylint_fail_under=8.0,
        provided={
            "max_complexity",
            "max_arguments",
            "type_checking",
            "bandit_severity",
            "bandit_confidence",
            "pylint_fail_under",
        },
    )

    cfg: Config = build_config(options)
    assert cfg.complexity.max_complexity == 7
    assert cfg.complexity.max_arguments == 4
    assert cfg.tool_settings["pylint"]["max-complexity"] == 7
    assert cfg.tool_settings["pylint"]["max-args"] == 4
    assert cfg.tool_settings["luacheck"]["max-cyclomatic-complexity"] == 7
    assert cfg.strictness.type_checking == "lenient"
    assert cfg.tool_settings["mypy"]["strict"] is False
    assert cfg.tool_settings["mypy"].get("ignore-missing-imports") is True
    for flag in [
        "warn-redundant-casts",
        "warn-unused-ignores",
        "warn-unreachable",
        "disallow-untyped-decorators",
        "disallow-any-generics",
        "check-untyped-defs",
        "no-implicit-reexport",
    ]:
        assert flag not in cfg.tool_settings["mypy"]
    assert cfg.tool_settings["tsc"]["strict"] is False
    assert cfg.severity.bandit_level == "high"
    assert cfg.severity.bandit_confidence == "low"
    assert cfg.tool_settings["bandit"]["severity"] == "high"
    assert cfg.tool_settings["bandit"]["confidence"] == "low"
    assert cfg.tool_settings["pylint"]["fail-under"] == 8.0


def test_sensitivity_low_adjusts_shared_knobs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home_dir)

    options = LintOptions(
        paths=[],
        root=tmp_path,
        changed_only=False,
        diff_ref="HEAD",
        include_untracked=True,
        base_branch=None,
        paths_from_stdin=False,
        provided={"sensitivity"},
        sensitivity="low",
    )

    cfg = build_config(options)

    assert cfg.execution.line_length == 140
    assert cfg.complexity.max_complexity == 15
    assert cfg.complexity.max_arguments == 7
    assert cfg.strictness.type_checking == "lenient"
    assert cfg.severity.bandit_level == "low"
    assert cfg.severity.bandit_confidence == "low"
    assert cfg.severity.pylint_fail_under == 8.0
    assert cfg.severity.max_warnings == 200
    assert cfg.tool_settings["mypy"].get("strict") is False
    assert cfg.tool_settings["mypy"].get("ignore-missing-imports") is True
    assert cfg.tool_settings["pylint"]["max-complexity"] == 15
    assert cfg.tool_settings["luacheck"]["max-cyclomatic-complexity"] == 15
    assert cfg.tool_settings["stylelint"]["max-warnings"] == 200
    assert cfg.tool_settings["bandit"]["severity"] == "low"
    assert cfg.tool_settings["bandit"]["confidence"] == "low"


def test_sensitivity_maximum_sets_ruff_select_all(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home_dir)

    options = LintOptions(
        paths=[],
        root=tmp_path,
        changed_only=False,
        diff_ref="HEAD",
        include_untracked=True,
        base_branch=None,
        paths_from_stdin=False,
        provided={"sensitivity"},
        sensitivity="maximum",
    )

    cfg = build_config(options)

    assert cfg.tool_settings["ruff"]["select"] == ["ALL"]
    assert cfg.tool_settings["pylint"]["init-import"] is True


def test_sensitivity_maximum_does_not_override_existing_ruff_select() -> None:
    cfg = Config()
    cfg.tool_settings.setdefault("ruff", {})["select"] = ["F", "E"]
    cfg.tool_settings.setdefault("pylint", {})["init-import"] = False
    cfg.severity.sensitivity = "maximum"

    cfg.apply_sensitivity_profile(cli_overrides=set())

    assert cfg.tool_settings["ruff"]["select"] == ["F", "E"]
    assert cfg.tool_settings["pylint"]["init-import"] is False


def test_sensitivity_respects_explicit_line_length_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home_dir)

    options = LintOptions(
        paths=[],
        root=tmp_path,
        changed_only=False,
        diff_ref="HEAD",
        include_untracked=True,
        base_branch=None,
        paths_from_stdin=False,
        line_length=150,
        provided={"sensitivity", "line_length"},
        sensitivity="maximum",
    )

    cfg = build_config(options)

    assert cfg.execution.line_length == 150
    assert cfg.complexity.max_complexity == 6
    assert cfg.complexity.max_arguments == 3
    assert cfg.strictness.type_checking == "strict"
    assert cfg.severity.bandit_level == "high"
    assert cfg.severity.max_warnings == 0
    assert cfg.tool_settings["black"]["line-length"] == 150
    assert cfg.tool_settings["stylelint"]["max-warnings"] == 0


def test_python_version_from_python_version_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home_dir)

    (tmp_path / ".python-version").write_text("3.11.4\n", encoding="utf-8")

    options = LintOptions(
        paths=[],
        root=tmp_path,
        changed_only=False,
        diff_ref="HEAD",
        include_untracked=True,
        base_branch=None,
        paths_from_stdin=False,
    )

    cfg = build_config(options)
    assert cfg.execution.python_version == "3.11"


def test_python_version_from_pyproject_overrides_all(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home_dir)

    (tmp_path / ".python-version").write_text("3.10.8\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
requires-python = ">=3.12"
""".strip(),
        encoding="utf-8",
    )

    options = LintOptions(
        paths=[],
        root=tmp_path,
        changed_only=False,
        diff_ref="HEAD",
        include_untracked=True,
        base_branch=None,
        paths_from_stdin=False,
    )

    cfg = build_config(options)
    assert cfg.execution.python_version == "3.12"
