# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""CLI command for updating dependencies across workspaces."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any, Final

import typer

from ..config_loader import ConfigError, ConfigLoader, ConfigLoadResult
from ..logging import fail, ok, warn
from ..process_utils import run_command
from ..update import (
    DEFAULT_STRATEGIES,
    CommandRunner,
    UpdateResult,
    Workspace,
    WorkspaceDiscovery,
    WorkspacePlanner,
    WorkspaceUpdater,
    ensure_lint_install,
)
from .typer_ext import create_typer

update_app = create_typer(name="update", help="Update dependencies across detected workspaces.")


def _default_runner(args: Sequence[str], cwd: Path | None) -> Any:
    return run_command(args, cwd=cwd, check=False)


@update_app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    root: Path = typer.Option(Path.cwd(), "--root", "-r", help="Project root to scan."),
    manager: list[str] | None = typer.Option(  # type: ignore[assignment]
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
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Print planned commands without executing.",
    ),
    emoji: bool = typer.Option(True, "--emoji/--no-emoji", help="Toggle emoji output."),
) -> None:
    if ctx.invoked_subcommand:
        return

    load_result = _load_update_configuration(root, emoji)
    update_config = load_result.config.update

    manager_filter = _normalise_cli_managers(manager, emoji)
    workspaces = _discover_workspaces(root, update_config.skip_patterns, emoji)
    planner = WorkspacePlanner(DEFAULT_STRATEGIES)
    config_enabled = _normalise_config_managers(update_config.enabled_managers, emoji)
    enabled_managers = manager_filter or config_enabled
    plan = planner.plan(workspaces, enabled_managers=enabled_managers)
    if not plan.items:
        warn("No workspaces selected for update.", use_emoji=emoji)
        raise typer.Exit(code=0)

    runner: CommandRunner = _default_runner
    updater = WorkspaceUpdater(runner=runner, dry_run=dry_run, use_emoji=emoji)
    if not skip_lint_install:
        ensure_lint_install(root, runner, dry_run=dry_run)

    result = updater.execute(plan, root=root)
    _emit_update_summary(result, dry_run=dry_run, use_emoji=emoji)


VALID_MANAGERS: Final[set[str]] = {strategy.kind.value for strategy in DEFAULT_STRATEGIES}


def _load_update_configuration(root: Path, use_emoji: bool) -> ConfigLoadResult:
    loader = ConfigLoader.for_root(root)
    try:
        return loader.load_with_trace()
    except ConfigError as exc:
        fail(f"Configuration invalid: {exc}", use_emoji=use_emoji)
        raise typer.Exit(code=1) from exc


def _normalise_cli_managers(values: list[str] | None, use_emoji: bool) -> set[str] | None:
    if not values:
        return None
    normalized = {value.lower() for value in values}
    invalid = sorted(normalized - VALID_MANAGERS)
    if invalid:
        fail(
            f"Unknown manager(s): {', '.join(invalid)}. Valid managers: {', '.join(sorted(VALID_MANAGERS))}",
            use_emoji=use_emoji,
        )
        raise typer.Exit(code=1)
    return normalized


def _discover_workspaces(
    root: Path,
    skip_patterns: Sequence[str],
    use_emoji: bool,
) -> list[Workspace]:
    discovery = WorkspaceDiscovery(strategies=DEFAULT_STRATEGIES, skip_patterns=skip_patterns)
    workspaces = discovery.discover(root)
    if not workspaces:
        warn("No workspaces discovered.", use_emoji=use_emoji)
        raise typer.Exit(code=0)
    return workspaces


def _normalise_config_managers(values: Sequence[str], use_emoji: bool) -> set[str] | None:
    if not values:
        return None
    normalized = {value.lower() for value in values}
    invalid = sorted(normalized - VALID_MANAGERS)
    if invalid:
        fail(
            f"Invalid manager(s) in configuration: {', '.join(invalid)}",
            use_emoji=use_emoji,
        )
        raise typer.Exit(code=1)
    return normalized


def _emit_update_summary(result: UpdateResult, *, dry_run: bool, use_emoji: bool) -> None:
    if dry_run:
        ok(
            f"Planned updates for {len(result.skipped)} workspace(s).",
            use_emoji=use_emoji,
        )
        raise typer.Exit(code=0)

    if result.failures:
        fail(
            f"Dependency updates failed for {len(result.failures)} workspace(s)",
            use_emoji=use_emoji,
        )
        raise typer.Exit(code=1)

    ok(
        f"Updated {len(result.successes)} workspace(s) successfully.",
        use_emoji=use_emoji,
    )
    raise typer.Exit(code=0)


__all__ = ["update_app"]
