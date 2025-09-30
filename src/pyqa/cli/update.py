# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""CLI command for updating dependencies across workspaces."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Final

import click
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


ROOT_OPTION = Annotated[
    Path,
    typer.Option(
        Path.cwd(),
        "--root",
        "-r",
        help="Project root to scan.",
        show_default=False,
    ),
]

MANAGER_OPTION = Annotated[
    list[str] | None,
    typer.Option(
        None,
        "--manager",
        "-m",
        help="Limit updates to specific managers (python, npm, pnpm, yarn, go, rust).",
    ),
]

SKIP_LINT_OPTION = Annotated[
    bool,
    typer.Option(
        False,
        "--skip-lint-install",
        help="Skip running the py-qa lint install bootstrap step.",
    ),
]

DRY_RUN_OPTION = Annotated[
    bool,
    typer.Option(
        False,
        "--dry-run",
        help="Print planned commands without executing.",
    ),
]

EMOJI_OPTION = Annotated[
    bool,
    typer.Option(True, "--emoji/--no-emoji", help="Toggle emoji output."),
]


@dataclass(slots=True)
class UpdateOptions:
    """Capture CLI options guiding the update workflow."""

    root: Path
    managers: list[str] | None
    skip_lint_install: bool
    dry_run: bool
    use_emoji: bool


def _default_runner(args: Sequence[str], cwd: Path | None) -> Any:
    """Return a command runner suitable for dependency update tasks.

    Args:
        args: Command arguments to execute.
        cwd: Working directory in which the command should run.

    Returns:
        Any: Completed process information emitted by :func:`run_command`.

    """

    return run_command(args, cwd=cwd, check=False)


@update_app.callback(invoke_without_command=True)
def main(
    root: ROOT_OPTION = Path.cwd(),
    manager: MANAGER_OPTION = None,
    skip_lint_install: SKIP_LINT_OPTION = False,
    dry_run: DRY_RUN_OPTION = False,
    emoji: EMOJI_OPTION = True,
) -> None:
    """Execute dependency updates across discovered workspaces.

    Args:
        root: Root directory to scan for workspaces.
        manager: Optional list of managers to include.
        skip_lint_install: Whether to skip bootstrapping lint dependencies.
        dry_run: When ``True``, emit planned commands without execution.
        emoji: Toggle emoji output for status messages.

    Returns:
        None: The Typer command exits the process via :func:`typer.Exit`.

    """

    if click.get_current_context().invoked_subcommand:
        return

    options = UpdateOptions(
        root=root.resolve(),
        managers=manager,
        skip_lint_install=skip_lint_install,
        dry_run=dry_run,
        use_emoji=emoji,
    )
    _run_update(options)


VALID_MANAGERS: Final[set[str]] = {strategy.kind.value for strategy in DEFAULT_STRATEGIES}


def _run_update(options: UpdateOptions) -> None:
    """Run the update workflow for the provided CLI options.

    Args:
        options: Parsed CLI options controlling update execution.

    Returns:
        None: Control flow terminates via :func:`typer.Exit`.

    """

    load_result = _load_update_configuration(options.root, options.use_emoji)
    update_config = load_result.config.update

    enabled_managers = _resolve_enabled_managers(
        options.managers,
        update_config.enabled_managers,
        use_emoji=options.use_emoji,
    )

    workspaces = _discover_workspaces(options.root, update_config.skip_patterns, options.use_emoji)
    planner = WorkspacePlanner(DEFAULT_STRATEGIES)
    plan = planner.plan(workspaces, enabled_managers=enabled_managers)
    if not plan.items:
        warn("No workspaces selected for update.", use_emoji=options.use_emoji)
        raise typer.Exit(code=0)

    runner: CommandRunner = _default_runner
    updater = WorkspaceUpdater(runner=runner, dry_run=options.dry_run, use_emoji=options.use_emoji)
    if not options.skip_lint_install:
        ensure_lint_install(options.root, runner, dry_run=options.dry_run)

    result = updater.execute(plan, root=options.root)
    _emit_update_summary(result, dry_run=options.dry_run, use_emoji=options.use_emoji)


def _load_update_configuration(root: Path, use_emoji: bool) -> ConfigLoadResult:
    """Load the py-qa configuration for the update workflow.

    Args:
        root: Project root containing the configuration files.
        use_emoji: Whether status output should include emoji glyphs.

    Returns:
        ConfigLoadResult: Loaded configuration and trace information.

    Raises:
        typer.Exit: When configuration resolution fails.

    """
    loader = ConfigLoader.for_root(root)
    try:
        return loader.load_with_trace()
    except ConfigError as exc:
        fail(f"Configuration invalid: {exc}", use_emoji=use_emoji)
        raise typer.Exit(code=1) from exc


def _normalise_cli_managers(values: list[str] | None, use_emoji: bool) -> set[str] | None:
    """Normalise manager names provided via CLI options.

    Args:
        values: Raw CLI input enumerating selected managers.
        use_emoji: Whether error output should include emoji glyphs.

    Returns:
        set[str] | None: Normalised manager names or ``None`` when not
        specified.

    Raises:
        typer.Exit: If unknown manager names are supplied.

    """
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
    """Discover workspaces eligible for dependency updates.

    Args:
        root: Root directory to scan for workspace definitions.
        skip_patterns: Glob patterns used to exclude paths from discovery.
        use_emoji: Whether warning output should include emoji glyphs.

    Returns:
        list[Workspace]: Discovered workspaces ready for planning.

    Raises:
        typer.Exit: If no workspaces are discovered.

    """
    discovery = WorkspaceDiscovery(strategies=DEFAULT_STRATEGIES, skip_patterns=skip_patterns)
    workspaces = discovery.discover(root)
    if not workspaces:
        warn("No workspaces discovered.", use_emoji=use_emoji)
        raise typer.Exit(code=0)
    return workspaces


def _resolve_enabled_managers(
    cli_values: list[str] | None,
    config_values: Sequence[str] | None,
    *,
    use_emoji: bool,
) -> set[str] | None:
    """Resolve enabled managers by combining CLI and configuration input.

    Args:
        cli_values: Raw manager names supplied via CLI options.
        config_values: Manager names declared in configuration files.
        use_emoji: Whether status output should include emoji glyphs.

    Returns:
        set[str] | None: Enabled manager names after reconciliation, or
        ``None`` when all managers should be considered.

    Raises:
        typer.Exit: If the CLI and configuration selections conflict.

    """

    cli_managers = _normalise_cli_managers(cli_values, use_emoji)
    config_managers = _normalise_config_managers(config_values, use_emoji)

    if cli_managers is None and config_managers is None:
        return None
    if cli_managers is None:
        return config_managers
    if config_managers is None:
        return cli_managers

    intersection = cli_managers & config_managers
    if not intersection:
        fail(
            "No overlap between CLI managers and configuration managers.",
            use_emoji=use_emoji,
        )
        raise typer.Exit(code=1)
    return intersection


def _normalise_config_managers(values: Sequence[str] | None, use_emoji: bool) -> set[str] | None:
    """Normalise manager names sourced from configuration files.

    Args:
        values: Manager names declared in configuration.
        use_emoji: Whether error output should include emoji glyphs.

    Returns:
        set[str] | None: Normalised manager names or ``None`` when the
        configuration does not constrain managers.

    Raises:
        typer.Exit: If invalid manager names are encountered.

    """
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
    """Render a summary of update execution results.

    Args:
        result: Aggregated execution outcome from :class:`WorkspaceUpdater`.
        dry_run: Whether commands were executed or only planned.
        use_emoji: Whether to include emoji glyphs in output.

    Returns:
        None: Control flow terminates via :func:`typer.Exit`.

    """
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
