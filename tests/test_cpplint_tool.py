# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Tests for cpplint tool integration."""

from __future__ import annotations

from pathlib import Path

from pyqa.catalog import ToolCatalogLoader
from pyqa.catalog.strategies import command_option_map
from pyqa.config import Config
from pyqa.tools.base import ToolAction, ToolContext

_PYQA_ROOT = Path(__file__).resolve().parents[1]
_CATALOG_ROOT = _PYQA_ROOT / "tooling" / "catalog"


def _cpplint_config() -> dict[str, object]:
    loader = ToolCatalogLoader(catalog_root=_CATALOG_ROOT)
    snapshot = loader.load_snapshot()
    for definition in snapshot.tools:
        if definition.name == "cpplint":
            return dict(definition.actions[0].command.reference.config)
    raise AssertionError("cpplint command configuration missing from catalog")


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

    builder = command_option_map(_cpplint_config())
    action = ToolAction(name="lint", command=builder, append_files=False)
    command = action.build_command(ctx)

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
    assert command[-1] == "--verbose=3"
