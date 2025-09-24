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
    assert cfg.tool_settings == {}
