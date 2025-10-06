# SPDX-License-Identifier: MIT

# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Tests for remark-lint tool integration."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import types
from unittest.mock import Mock

_stub_spacy = types.ModuleType("spacy")
_stub_spacy.__version__ = "0.0.0"


def _stub_load(name: str):  # pragma: no cover - helper for stub module
    raise OSError(f"spaCy model '{name}' unavailable in tests")


_stub_spacy.load = _stub_load  # type: ignore[attr-defined]
sys.modules.setdefault("spacy", _stub_spacy)

from pyqa.config import Config
from pyqa.orchestration.action_executor import (
    ActionExecutor,
    ActionInvocation,
    ExecutionEnvironment,
)
from pyqa.cache.context import CacheContext
from pyqa.catalog import ToolCatalogLoader
from pyqa.catalog.strategies import command_option_map
from pyqa.tools.base import ToolAction, ToolContext

_PYQA_ROOT = Path(__file__).resolve().parents[1]
_CATALOG_ROOT = _PYQA_ROOT / "tooling" / "catalog"


def _remark_config(action: str) -> dict[str, object]:
    loader = ToolCatalogLoader(catalog_root=_CATALOG_ROOT)
    snapshot = loader.load_snapshot()
    for definition in snapshot.tools:
        if definition.name != "remark-lint":
            continue
        for candidate in definition.actions:
            if candidate.name == action:
                return dict(candidate.command.reference.config)
    raise AssertionError(
        f"remark-lint command configuration for action '{action}' missing from catalog",
    )


def test_remark_lint_command_build(tmp_path: Path) -> None:
    cfg = Mock()
    cfg.execution.line_length = 120
    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[tmp_path / "README.md"],
        settings={
            "config": tmp_path / ".remarkrc.json",
            "use": ["remark-lint-ordered-list-marker-style"],
            "setting": ["listItemIndent=one"],
        },
    )

    builder = command_option_map(_remark_config("lint"))
    action = ToolAction(name="lint", command=builder, append_files=False)

    cmd = action.build_command(ctx)
    assert cmd[0] == "remark"
    assert "--report" in cmd and "json" in cmd
    assert "--use" in cmd and "remark-lint-ordered-list-marker-style" in cmd
    assert "--config" in cmd and str((tmp_path / ".remarkrc.json").resolve()) in cmd
    assert cmd[-1].endswith("README.md")


def test_remark_fix_command_build(tmp_path: Path) -> None:
    cfg = Mock()
    cfg.execution.line_length = 120
    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[tmp_path / "README.md"],
        settings={},
    )

    builder = command_option_map(_remark_config("fix"))
    action = ToolAction(name="fix", command=builder, append_files=False)

    cmd = action.build_command(ctx)
    assert cmd[0] == "remark"
    assert cmd[-1] == "--output"
    assert cmd[-2] == (tmp_path / "README.md").as_posix()


def test_remark_fix_rewrites_file_in_place(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    markdown_file = tmp_path / "docs" / "note.md"
    markdown_file.write_text("# Title\n\n-  list\n", encoding="utf-8")

    cfg = Config()
    cache = CacheContext(cache=None, token=None, cache_dir=tmp_path, versions={})
    environment = ExecutionEnvironment(
        config=cfg,
        root=tmp_path,
        severity_rules={},
        cache=cache,
    )

    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[markdown_file],
        settings={},
    )

    builder = command_option_map(_remark_config("fix"))
    action = ToolAction(name="fix", command=builder, append_files=False)
    invocation = ActionInvocation(
        tool_name="remark-lint",
        action=action,
        context=ctx,
        command=action.build_command(ctx),
        env_overrides={},
    )

    def fake_runner(cmd, **_kwargs):
        assert cmd[0] == "remark"
        assert cmd[-1] == "--output"
        assert cmd.count("--output") == 1

        file_position = cmd.index(markdown_file.as_posix())
        output_position = cmd.index("--output")

        if output_position < file_position:
            relocated = markdown_file.parent.parent / markdown_file.name
            relocated.write_text("broken", encoding="utf-8")
        else:
            markdown_file.write_text("# Title\n\n- list\n", encoding="utf-8")

        return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

    executor = ActionExecutor(runner=fake_runner, after_tool_hook=None)
    outcome = executor.run_action(invocation, environment)

    assert outcome.returncode == 0
    assert markdown_file.read_text(encoding="utf-8") == "# Title\n\n- list\n"
    assert not any(path.parent == tmp_path for path in tmp_path.iterdir() if path.is_file())
