# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Tests for cpplint tool integration."""

from __future__ import annotations

from pathlib import Path

from pyqa.config import Config
from pyqa.tooling.strategies import cpplint_command
from pyqa.tools.base import ToolContext


def test_cpplint_command_build(tmp_path: Path) -> None:
    cfg = Config()
    cfg.execution.line_length = 110
    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[tmp_path / "src" / "foo.cc"],
        settings={
            "line-length": 140,
            "filter": ["-whitespace"],
            "exclude": [tmp_path / "vendor" / "lib.cc"],
            "extensions": ["cc", "hh"],
            "headers": ["hh"],
            "recursive": True,
            "counting": "detailed",
            "includeorder": "standardcfirst",
            "args": ["--verbose=3"],
        },
    )

    builder = cpplint_command({"base": ["cpplint", "--output=emacs"]})
    command = list(builder.build(ctx))
    command.extend(str(path) for path in ctx.files)
    assert command[0] == "cpplint"
    assert "--output=emacs" in command
    assert "--linelength=140" in command
    assert any(part.startswith("--filter=") for part in command)
    assert any(part.startswith("--exclude=") for part in command)
    assert any(part.startswith("--extensions=") for part in command)
    assert any(part.startswith("--headers=") for part in command)
    assert "--recursive" in command
    assert "--counting=detailed" in command
    assert "--includeorder=standardcfirst" in command
    assert command[-1].endswith("foo.cc")
