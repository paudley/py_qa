"""Tests for golangci-lint command builder."""

from __future__ import annotations

from pathlib import Path

from pyqa.config import Config
from pyqa.tools.base import ToolAction, ToolContext
from pyqa.tools.builtins import _GolangciLintCommand


def test_golangci_command_includes_enable_all(tmp_path: Path) -> None:
    cfg = Config()
    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[tmp_path / "main.go"],
        settings={"disable": ["govet"], "enable": ["gofmt"]},
    )

    action = ToolAction(
        name="lint",
        command=_GolangciLintCommand(base=("golangci-lint", "run", "--out-format", "json")),
        append_files=False,
    )

    command = action.build_command(ctx)
    assert "--enable-all" in command
    assert "--disable" in command


def test_golangci_respects_disable_enable_all_flag(tmp_path: Path) -> None:
    cfg = Config()
    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[tmp_path / "main.go"],
        settings={"enable-all": False},
    )

    action = ToolAction(
        name="lint",
        command=_GolangciLintCommand(base=("golangci-lint", "run", "--out-format", "json")),
        append_files=False,
    )

    command = action.build_command(ctx)
    assert "--enable-all" not in command
