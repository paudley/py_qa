# SPDX-License-Identifier: MIT
"""CLI command for updating dependencies across workspaces."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, List, Optional, Sequence

import typer

from ..config_loader import ConfigError, ConfigLoader
from ..logging import fail, ok, warn
from ..update import (
    DEFAULT_STRATEGIES,
    WorkspaceDiscovery,
    WorkspacePlanner,
    WorkspaceUpdater,
    ensure_lint_install,
)

CommandRunner = Callable[[Sequence[str], Path | None], object]

update_app = typer.Typer(
    name="update", help="Update dependencies across detected workspaces."
)


def _default_runner(args: Sequence[str], cwd: Path | None):
    from subprocess import run

    return run(args, cwd=cwd, check=False, text=True)


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
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Print planned commands without executing."
    ),
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

    update_config = load_result.config.update

    valid_managers = {strategy.kind for strategy in DEFAULT_STRATEGIES}

    manager_filter: set[str] | None = None
    if manager:
        normalized = {value.lower() for value in manager}
        invalid = sorted(normalized - valid_managers)
        if invalid:
            fail(
                f"Unknown manager(s): {', '.join(invalid)}. Valid managers: {', '.join(sorted(valid_managers))}",
                use_emoji=emoji,
            )
            raise typer.Exit(code=1)
        manager_filter = normalized

    discovery = WorkspaceDiscovery(
        strategies=DEFAULT_STRATEGIES,
        skip_patterns=update_config.skip_patterns,
    )
    workspaces = discovery.discover(root)
    if not workspaces:
        warn("No workspaces discovered.", use_emoji=emoji)
        raise typer.Exit(code=0)

    planner = WorkspacePlanner(DEFAULT_STRATEGIES)
    config_enabled: set[str] | None = None
    if update_config.enabled_managers:
        normalized = {value.lower() for value in update_config.enabled_managers}
        invalid = sorted(normalized - valid_managers)
        if invalid:
            fail(
                f"Invalid manager(s) in configuration: {', '.join(invalid)}",
                use_emoji=emoji,
            )
            raise typer.Exit(code=1)
        config_enabled = normalized

    enabled = manager_filter or config_enabled
    plan = planner.plan(workspaces, enabled_managers=enabled)
    if not plan.items:
        warn("No workspaces selected for update.", use_emoji=emoji)
        raise typer.Exit(code=0)

    runner: CommandRunner = _default_runner
    updater = WorkspaceUpdater(runner=runner, dry_run=dry_run, use_emoji=emoji)
    if not skip_lint_install:
        ensure_lint_install(root, runner, dry_run=dry_run)

    result = updater.execute(plan, root=root)

    if dry_run:
        ok(
            f"Planned updates for {len(result.skipped)} workspace(s).",
            use_emoji=emoji,
        )
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
