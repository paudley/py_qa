"""Tests for kube-linter tool integration."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest

from pyqa.tools.base import ToolAction, ToolContext
from pyqa.tools.builtins import (
    KUBE_LINTER_VERSION_DEFAULT,
    _KubeLinterCommand,
)


def test_kube_linter_command_download(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    binary_path = tmp_path / "bin" / "kube-linter"
    binary_path.parent.mkdir(parents=True, exist_ok=True)
    binary_path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")

    monkeypatch.setattr(
        "pyqa.tools.builtins._ensure_kube_linter",
        lambda version, cache_root: binary_path,
    )

    cfg = Mock()
    cfg.execution.line_length = 120

    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[tmp_path / "manifests" / "deployment.yaml"],
        settings={"config": tmp_path / "config" / "custom.yaml", "include": ["check-a"], "verbose": True},
    )

    action = ToolAction(
        name="lint",
        command=_KubeLinterCommand(
            base=("kube-linter", "lint", "--format", "json"),
            version=KUBE_LINTER_VERSION_DEFAULT,
        ),
        append_files=True,
    )

    command = action.build_command(ctx)
    assert command[0] == str(binary_path)
    assert "--format" in command and "json" in command
    assert "--config" in command
    assert str(tmp_path / "config" / "custom.yaml") in command
    assert command[-1].endswith("deployment.yaml")
