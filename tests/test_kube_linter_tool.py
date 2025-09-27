# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Tests for kube-linter tool integration."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

from pyqa.tools.base import ToolAction, ToolContext
from pyqa.tools.builtins import KubeLinterCommand


def test_kube_linter_command_build(tmp_path: Path) -> None:
    cfg = Mock()
    cfg.execution.line_length = 120

    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[tmp_path / "manifests" / "deployment.yaml"],
        settings={
            "config": tmp_path / "config" / "custom.yaml",
            "include": ["check-a"],
            "verbose": True,
        },
    )

    action = ToolAction(
        name="lint",
        command=KubeLinterCommand(base=("kube-linter", "lint", "--format", "json")),
        append_files=True,
    )

    command = action.build_command(ctx)
    assert tuple(command[:4]) == ("kube-linter", "lint", "--format", "json")
    assert "--config" in command
    assert str(tmp_path / "config" / "custom.yaml") in command
    assert command[-1].endswith("deployment.yaml")
