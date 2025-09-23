# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Tests for the actionlint tool integration."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest

from pyqa.tools.base import ToolContext
from pyqa.tools.builtins import _ActionlintCommand


def test_actionlint_command_download(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    binary_path = tmp_path / "bin" / "actionlint"
    binary_path.parent.mkdir(parents=True, exist_ok=True)
    binary_path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")

    monkeypatch.setattr(
        "pyqa.tools.builtins._ensure_actionlint",
        lambda version, cache_root: binary_path,
    )

    cfg = Mock()
    cfg.execution.line_length = 120

    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[],
        settings={},
    )

    (tmp_path / ".github" / "workflows").mkdir(parents=True)

    command = _ActionlintCommand(version="1.7.1").build(ctx)
    assert command[0] == str(binary_path)
    assert command[-1].endswith(".github/workflows")
