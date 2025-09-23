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

    assert cfg.file_discovery.roots == [tmp_path.resolve()]
    assert cfg.file_discovery.diff_ref == "HEAD"
    assert not cfg.execution.only
    assert not cfg.execution.languages
    assert not cfg.execution.fix_only
    assert not cfg.execution.check_only
    assert cfg.execution.jobs == 2
    assert not cfg.execution.cache_enabled
    assert cfg.execution.cache_dir == tmp_path / ".cache"
    assert not cfg.execution.bail
    assert not cfg.execution.use_local_linters
    assert cfg.output.pr_summary_limit == 100
    assert cfg.output.pr_summary_min_severity == "warning"
    assert cfg.output.pr_summary_template
    assert not cfg.output.quiet
    assert cfg.output.tool_filters == DEFAULT_TOOL_FILTERS
    assert cfg.output.output == "concise"
    assert cfg.output.color
    assert cfg.output.emoji
    exclude_names = {path.name for path in cfg.file_discovery.excludes}
    assert ".lint-cache" in exclude_names
    assert ".cache" in exclude_names
    assert cfg.tool_settings == {}
