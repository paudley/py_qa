# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Tests for the dependency update command."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Sequence

from typer.testing import CliRunner

from pyqa.cli.app import app
from pyqa.update import (
    DEFAULT_STRATEGIES,
    WorkspaceDiscovery,
    WorkspaceKind,
    WorkspacePlanner,
    WorkspaceUpdater,
)


class RecordingRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[str, ...], Path]] = []

    def __call__(self, args: Sequence[str], cwd: Path | None):
        self.calls.append((tuple(args), cwd or Path.cwd()))

        class Result:
            returncode = 0

        return Result()


def _write_repo(root: Path) -> None:
    # Python project
    (root / "service").mkdir(parents=True, exist_ok=True)
    (root / "service" / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")

    # Node project with pnpm
    (root / "ui").mkdir(parents=True, exist_ok=True)
    (root / "ui" / "package.json").write_text("{}\n", encoding="utf-8")
    (root / "ui" / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")

    # Go project
    (root / "tooling").mkdir(parents=True, exist_ok=True)
    (root / "tooling" / "go.mod").write_text("module example.com/tooling\n", encoding="utf-8")


def test_workspace_discovery_identifies_managers(tmp_path: Path) -> None:
    _write_repo(tmp_path)
    discovery = WorkspaceDiscovery()
    workspaces = discovery.discover(tmp_path)
    kinds = {(ws.kind, ws.directory.relative_to(tmp_path)) for ws in workspaces}
    assert (WorkspaceKind.PYTHON, Path("service")) in kinds
    assert (WorkspaceKind.PNPM, Path("ui")) in kinds
    assert (WorkspaceKind.GO, Path("tooling")) in kinds


def test_python_workspace_runs_uv_commands(tmp_path: Path, monkeypatch) -> None:
    _write_repo(tmp_path)
    runner = RecordingRunner()
    updater = WorkspaceUpdater(runner=runner, dry_run=False, use_emoji=False)

    # Pretend pnpm/go/uv binaries exist so strategies are active
    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/mock" if cmd in {"pnpm", "go", "uv"} else None)

    discovery = WorkspaceDiscovery()
    workspaces = discovery.discover(tmp_path)
    python_ws = next(ws for ws in workspaces if ws.kind == WorkspaceKind.PYTHON)

    planner = WorkspacePlanner(DEFAULT_STRATEGIES)
    plan = planner.plan([python_ws])
    updater.execute(plan, root=tmp_path)

    commands = [call[0] for call in runner.calls]
    assert ("uv", "venv") in commands
    assert (
        "uv",
        "sync",
        "-U",
        "--all-extras",
        "--all-groups",
        "--managed-python",
        "--link-mode=hardlink",
        "--compile-bytecode",
    ) in commands


def test_update_cli_dry_run(tmp_path: Path, monkeypatch) -> None:
    _write_repo(tmp_path)

    monkeypatch.setenv("PATH", "/usr/bin")
    # Ensure commands appear available
    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/mock")

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "update",
            "--root",
            str(tmp_path),
            "--dry-run",
            "--no-emoji",
        ],
    )

    assert result.exit_code == 0
    assert "DRY RUN" in result.stdout
