# SPDX-License-Identifier: MIT

# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Tests for ESLint command strategy."""

from __future__ import annotations

from pathlib import Path

from pyqa.config import Config
from pyqa.tooling import ToolCatalogLoader
from pyqa.tooling.strategies import command_option_map
from pyqa.tools.base import ToolAction, ToolContext

_PYQA_ROOT = Path(__file__).resolve().parents[1]
_CATALOG_ROOT = _PYQA_ROOT / "tooling" / "catalog"


def _eslint_command_config(action: str) -> dict[str, object]:
    loader = ToolCatalogLoader(catalog_root=_CATALOG_ROOT)
    snapshot = loader.load_snapshot()
    for definition in snapshot.tools:
        if definition.name != "eslint":
            continue
        for candidate in definition.actions:
            if candidate.name == action:
                return dict(candidate.command.reference.config)
    raise AssertionError(f"eslint command configuration for action '{action}' missing from catalog")


def test_eslint_lint_command_build(tmp_path: Path) -> None:
    cfg = Config()
    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[tmp_path / "src" / "app.ts"],
        settings={
            "config": tmp_path / ".eslintrc.js",
            "ext": [".ts", ".tsx"],
            "rulesdir": ["rules"],
            "cache": False,
            "cache-location": tmp_path / ".cache" / "eslint",
            "quiet": True,
            "no-error-on-unmatched-pattern": False,
            "args": ["src"],
        },
    )

    builder = command_option_map(_eslint_command_config("lint"))
    action = ToolAction(name="lint", command=builder)

    command = action.build_command(ctx)
    assert command[:3] == ["eslint", "--format", "json"]
    assert "--config" in command and str((tmp_path / ".eslintrc.js").resolve()) in command
    assert "--ext" in command and command.count("--ext") == 2
    assert "--rulesdir" in command
    assert "--no-cache" in command
    assert "--cache-location" in command
    assert "--error-on-unmatched-pattern" in command  # lint mode retains strict behaviour
    assert command[-1].endswith("app.ts")


def test_eslint_fix_command_build(tmp_path: Path) -> None:
    cfg = Config()
    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[tmp_path / "src" / "app.ts"],
        settings={
            "args": ["src"],
            "no-error-on-unmatched-pattern": False,
        },
    )

    builder = command_option_map(_eslint_command_config("fix"))
    action = ToolAction(name="fix", command=builder, append_files=False)

    command = action.build_command(ctx)
    assert command[:2] == ["eslint", "--fix"]
    assert "--error-on-unmatched-pattern" not in command


def test_eslint_defaults_max_warnings(tmp_path: Path) -> None:
    cfg = Config()
    cfg.severity.max_warnings = 3
    builder = command_option_map(_eslint_command_config("lint"))
    action = ToolAction(name="lint", command=builder, ignore_exit=True)
    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[tmp_path / "src" / "app.ts"],
        settings=cfg.tool_settings.setdefault("eslint", {}),
    )

    command = action.build_command(ctx)
    assert "--max-warnings" in command and "3" in command

    cfg_default = Config()
    action_default = ToolAction(name="lint", command=builder, ignore_exit=True)
    ctx_default = ToolContext(
        cfg=cfg_default,
        root=tmp_path,
        files=[tmp_path / "src" / "app.ts"],
        settings=cfg_default.tool_settings.setdefault("eslint", {}),
    )

    command_default = action_default.build_command(ctx_default)
    assert "--max-warnings" not in command_default
