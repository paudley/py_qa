# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""CLI command for updating dependencies across workspaces."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable, List, Optional, Sequence

import typer

from ..config_loader import ConfigError, ConfigLoader
from ..logging import fail, ok, warn
from ..update import (
    WorkspaceDiscovery,
    WorkspaceKind,
    WorkspaceUpdater,
    ensure_lint_install,
)

CommandRunner = Callable[[Sequence[str], Path | None], subprocess.CompletedProcess[str]]

update_app = typer.Typer(name="update", help="Update dependencies across detected workspaces.")


def _default_runner(args: Sequence[str], cwd: Path | None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, check=False, text=True)


@update_app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    root: Path = typer.Option(Path.cwd(), "--root", "-r", help="Project root to scan."),
    manager: Optional[List[str]] = typer.Option(  # type: ignore[assignment]
        None,
        "--manager",
        "-m",
        help="Limit updates to specific managers (python, npm, pnpm, yarn, go, rust).",
    ),
    skip_lint_install: bool = typer.Option(
        False,
        "--skip-lint-install",
        help="Skip running the py-qa lint install bootstrap step.",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print planned commands without executing."),
    emoji: bool = typer.Option(True, "--emoji/--no-emoji", help="Toggle emoji output."),
) -> None:
    if ctx.invoked_subcommand:
        return

    loader = ConfigLoader.for_root(root)
    try:
        load_result = loader.load_with_trace()
    except ConfigError as exc:
        fail(f"Configuration invalid: {exc}", use_emoji=emoji)
        raise typer.Exit(code=1) from exc

    if load_result.warnings:
        for message in load_result.warnings:
            warn(message, use_emoji=emoji)

    manager_filter: set[WorkspaceKind] | None = None
    if manager:
        try:
            manager_filter = {WorkspaceKind(value.lower()) for value in manager}
        except ValueError as exc:
            valid = ", ".join(kind.value for kind in WorkspaceKind)
            fail(f"{exc}. Valid managers: {valid}", use_emoji=emoji)
            raise typer.Exit(code=1) from exc

    discovery = WorkspaceDiscovery()
    workspaces = discovery.discover(root)
    if not workspaces:
        warn("No workspaces discovered.", use_emoji=emoji)
        raise typer.Exit(code=0)

    runner: CommandRunner = _default_runner
    updater = WorkspaceUpdater(runner=runner, dry_run=dry_run, use_emoji=emoji)
    if not skip_lint_install:
        ensure_lint_install(root, runner, dry_run=dry_run)

    result = updater.update(
        root,
        managers=manager_filter,
        workspaces=workspaces,
    )

    if dry_run:
        ok(f"Planned updates for {len(result.skipped)} workspace(s).", use_emoji=emoji)
        raise typer.Exit(code=0)

    if result.failures:
        fail(
            f"Dependency updates failed for {len(result.failures)} workspace(s)",
            use_emoji=emoji,
        )
        raise typer.Exit(code=1)

    ok(
        f"Updated {len(result.successes)} workspace(s) successfully.",
        use_emoji=emoji,
    )
    raise typer.Exit(code=0)


__all__ = ["update_app"]
