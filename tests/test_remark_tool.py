"""Tests for remark-lint tool integration."""

from __future__ import annotations

from pathlib import Path

from pyqa.config import Config
from pyqa.tools.base import ToolAction, ToolContext
from pyqa.tools.builtins import _RemarkCommand


def test_remark_lint_command_build(tmp_path: Path) -> None:
    cfg = Config()
    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[tmp_path / "README.md"],
        settings={"config": tmp_path / ".remarkrc.json", "use": ["remark-lint-ordered-list-marker-style"]},
    )

    action = ToolAction(
        name="lint",
        command=_RemarkCommand(base=("remark", "--use", "remark-preset-lint-recommended")),
        append_files=True,
    )

    cmd = action.build_command(ctx)
    assert cmd[0] == "remark"
    assert "--report" in cmd and "json" in cmd
    assert "--use" in cmd
    assert "--config" in cmd
    assert cmd[-1].endswith("README.md")


def test_remark_fix_command_build(tmp_path: Path) -> None:
    cfg = Config()
    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[tmp_path / "README.md"],
        settings={"args": ["--setting", "listItemIndent=one"]},
    )

    action = ToolAction(
        name="fix",
        command=_RemarkCommand(base=("remark", "--use", "remark-preset-lint-recommended"), is_fix=True),
        append_files=True,
        is_fix=True,
    )

    cmd = action.build_command(ctx)
    assert cmd[0] == "remark"
    assert "--output" in cmd
    assert "--report" not in cmd
    assert cmd[-1].endswith("README.md")
