# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Tests covering CLI configuration helpers."""

from pathlib import Path

import pytest

from pyqa.cli.core.config_builder import DEFAULT_TOOL_FILTERS, build_config
from pyqa.cli.core.options import (
    ExecutionFormattingOptions,
    ExecutionRuntimeOptions,
    LintComplexityOptions,
    LintDisplayOptions,
    LintExecutionOptions,
    LintGitOptions,
    LintOptionBundles,
    LintOptions,
    LintOutputBundle,
    LintOverrideOptions,
    LintSelectionOptions,
    LintSeverityOptions,
    LintStrictnessOptions,
    LintSummaryOptions,
    LintTargetOptions,
)
from pyqa.config import Config
from pyqa.interfaces.config import ConfigSource


def _build_options(
    root: Path,
    *,
    provided: set[str] | None = None,
    paths: list[Path] | None = None,
    dirs: list[Path] | None = None,
    exclude: list[Path] | None = None,
    paths_from_stdin: bool = False,
    include_dotfiles: bool = False,
    changed_only: bool = False,
    diff_ref: str = "HEAD",
    include_untracked: bool = True,
    base_branch: str | None = None,
    no_lint_tests: bool = False,
    filters: list[str] | None = None,
    only: list[str] | None = None,
    language: list[str] | None = None,
    fix_only: bool = False,
    check_only: bool = False,
    verbose: bool = False,
    quiet: bool = False,
    no_color: bool = False,
    no_emoji: bool = False,
    output_mode: str = "concise",
    advice: bool = False,
    show_passing: bool = False,
    no_stats: bool = False,
    pr_summary_out: Path | None = None,
    pr_summary_limit: int = 100,
    pr_summary_min_severity: str = "warning",
    pr_summary_template: str = "- {message}",
    jobs: int | None = None,
    bail: bool = False,
    no_cache: bool = False,
    cache_dir: Path | None = None,
    use_local_linters: bool = False,
    strict_config: bool = False,
    line_length: int = 120,
    sql_dialect: str = "postgresql",
    python_version: str | None = None,
    max_complexity: int | None = None,
    max_arguments: int | None = None,
    type_checking: str | None = None,
    bandit_severity: str | None = None,
    bandit_confidence: str | None = None,
    pylint_fail_under: float | None = None,
    sensitivity: str | None = None,
) -> LintOptions:
    target = LintTargetOptions(
        root=root,
        paths=list(paths or []),
        dirs=list(dirs or []),
        exclude=list(exclude or []),
        paths_from_stdin=paths_from_stdin,
        include_dotfiles=include_dotfiles,
    )
    git = LintGitOptions(
        changed_only=changed_only,
        diff_ref=diff_ref,
        include_untracked=include_untracked,
        base_branch=base_branch,
        no_lint_tests=no_lint_tests,
    )
    selection = LintSelectionOptions(
        filters=list(filters or []),
        only=list(only or []),
        language=list(language or []),
        fix_only=fix_only,
        check_only=check_only,
    )
    display = LintDisplayOptions(
        verbose=verbose,
        quiet=quiet,
        no_color=no_color,
        no_emoji=no_emoji,
        output_mode=output_mode,
        debug=False,
        advice=advice,
    )
    summary = LintSummaryOptions(
        show_passing=show_passing,
        no_stats=no_stats,
        pr_summary_out=pr_summary_out,
        pr_summary_limit=pr_summary_limit,
        pr_summary_min_severity=pr_summary_min_severity,
        pr_summary_template=pr_summary_template,
    )
    output = LintOutputBundle(display=display, summary=summary)

    runtime = ExecutionRuntimeOptions(
        jobs=jobs,
        bail=bail,
        no_cache=no_cache,
        cache_dir=cache_dir or root / ".lint-cache",
        use_local_linters=use_local_linters,
        strict_config=strict_config,
    )
    formatting = ExecutionFormattingOptions(
        line_length=line_length,
        sql_dialect=sql_dialect,
        python_version=python_version,
    )
    execution = LintExecutionOptions(runtime=runtime, formatting=formatting)

    complexity = LintComplexityOptions(
        max_complexity=max_complexity,
        max_arguments=max_arguments,
    )
    strictness = LintStrictnessOptions(type_checking=type_checking)
    severity = LintSeverityOptions(
        bandit_severity=bandit_severity,
        bandit_confidence=bandit_confidence,
        pylint_fail_under=pylint_fail_under,
        sensitivity=sensitivity,
    )
    overrides = LintOverrideOptions(
        complexity=complexity,
        strictness=strictness,
        severity=severity,
    )

    bundles = LintOptionBundles(
        targets=target,
        git=git,
        selection=selection,
        output=output,
        execution=execution,
        overrides=overrides,
    )
    return LintOptions(bundles=bundles, provided=provided or set())


class _StubSource(ConfigSource):
    def __init__(self, payload: dict[str, object], *, name: str = "stub") -> None:
        self.name = name
        self._payload = payload

    def load(self) -> dict[str, object]:
        return self._payload

    def describe(self) -> str:
        return f"Stub source {self.name}"


def test_build_config_defaults(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure CLI option translation produces a fully populated config."""
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home_dir)

    options = _build_options(
        tmp_path,
        jobs=2,
        no_cache=True,
        cache_dir=tmp_path / ".cache",
        pr_summary_template="- {message}",
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
    assert "strict" not in cfg.tool_settings["mypy"]
    assert cfg.tool_settings["mypy"]["show-error-codes"] is True
    assert cfg.complexity.max_complexity == 10
    assert cfg.complexity.max_arguments == 5
    assert cfg.tool_settings.get("bandit", {}).get("severity") is None
    assert cfg.tool_settings.get("bandit", {}).get("confidence") is None
    assert cfg.severity.pylint_fail_under == 9.5
    assert "ruff" in cfg.dedupe.dedupe_prefer
    assert "pyright" in cfg.dedupe.dedupe_prefer


def test_build_config_accepts_protocol_sources(tmp_path: Path) -> None:
    options = _build_options(tmp_path)
    custom_source = _StubSource({"execution": {"jobs": 11}})

    cfg = build_config(options, sources=[custom_source])

    assert cfg.execution.jobs == 11


def test_build_config_cli_overrides_complexity_and_strictness(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home_dir)

    options = _build_options(
        tmp_path,
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
    assert cfg.complexity.max_complexity == 7
    assert cfg.complexity.max_arguments == 4
    assert cfg.strictness.type_checking == "lenient"
    assert "strict" not in cfg.tool_settings["mypy"]
    assert cfg.tool_settings["mypy"].get("ignore-missing-imports") is None
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
    assert cfg.severity.bandit_level == "high"
    assert cfg.severity.bandit_confidence == "low"
    assert cfg.severity.pylint_fail_under == 8.0


def test_sensitivity_low_adjusts_shared_knobs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home_dir)

    options = _build_options(
        tmp_path,
        sensitivity="low",
        provided={"sensitivity"},
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
    assert "strict" not in cfg.tool_settings["mypy"]
    assert cfg.tool_settings["mypy"].get("ignore-missing-imports") is None
    assert cfg.tool_settings.get("tsc", {}).get("strict") is None
    assert cfg.tool_settings.get("stylelint", {}).get("max-warnings") is None
    assert cfg.tool_settings.get("bandit", {}).get("severity") is None
    assert cfg.tool_settings.get("bandit", {}).get("confidence") is None


def test_sensitivity_maximum_sets_ruff_select_all(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home_dir)

    options = _build_options(
        tmp_path,
        sensitivity="maximum",
        provided={"sensitivity"},
    )

    cfg = build_config(options)

    assert cfg.tool_settings["ruff"]["select"] == ["ALL"]
    assert cfg.tool_settings.get("pylint", {}).get("init-import") is True


def test_sensitivity_maximum_does_not_override_existing_ruff_select() -> None:
    cfg = Config()
    cfg.tool_settings.setdefault("ruff", {})["select"] = ["F", "E"]
    cfg.tool_settings.setdefault("pylint", {})["init-import"] = False
    cfg.severity.sensitivity = "maximum"

    cfg.apply_sensitivity_profile(cli_overrides=set())

    assert cfg.tool_settings["ruff"]["select"] == ["F", "E"]
    assert cfg.tool_settings.get("pylint", {}).get("init-import") is False


def test_sensitivity_respects_explicit_line_length_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home_dir)

    options = _build_options(
        tmp_path,
        line_length=150,
        sensitivity="maximum",
        provided={"sensitivity", "line_length"},
    )

    cfg = build_config(options)

    assert cfg.execution.line_length == 150
    assert cfg.complexity.max_complexity == 6
    assert cfg.complexity.max_arguments == 3
    assert cfg.strictness.type_checking == "strict"
    assert cfg.severity.bandit_level == "high"
    assert cfg.severity.max_warnings == 0
    assert cfg.execution.line_length == 150
    assert cfg.severity.max_warnings == 0


def test_python_version_from_python_version_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home_dir)

    (tmp_path / ".python-version").write_text("3.11.4\n", encoding="utf-8")

    options = _build_options(tmp_path)

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

    options = _build_options(tmp_path)

    cfg = build_config(options)
    assert cfg.execution.python_version == "3.12"
