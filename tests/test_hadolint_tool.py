# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Tests for hadolint tool integration."""

from __future__ import annotations

from pathlib import Path

import pytest

from pyqa.config import Config
from pyqa.tools.base import ToolAction, ToolContext
from pyqa.tools.builtins import HADOLINT_VERSION_DEFAULT, _HadolintCommand


def test_hadolint_command_download(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake_binary = tmp_path / "bin" / "hadolint"
    fake_binary.parent.mkdir(parents=True, exist_ok=True)
    fake_binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake_binary.chmod(0o755)

    monkeypatch.setattr(
        "pyqa.tools.builtin_commands_misc.ensure_hadolint",
        lambda version, cache_root: fake_binary,
    )

    cfg = Config()
    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[tmp_path / "Dockerfile"],
        settings={"config": tmp_path / ".hadolint"},
    )

    action = ToolAction(
        name="lint",
        command=_HadolintCommand(version=HADOLINT_VERSION_DEFAULT),
        append_files=True,
    )

    command = action.build_command(ctx)
    assert command[0] == str(fake_binary)
    assert "--format" in command and "json" in command
    assert "--config" in command and str(tmp_path / ".hadolint") in command
    assert command[-1].endswith("Dockerfile")
