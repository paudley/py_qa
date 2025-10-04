# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""CLI command for updating dependencies across workspaces."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Annotated, Any, Final, Literal, cast

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
from ._update_cli_models import UpdateOptions, build_update_options
from .shared import Depends
from .typer_ext import create_typer

update_app = create_typer(name="update", help="Update dependencies across detected workspaces.")

ManagerNameLiteral = Literal["go", "rust", "yarn", "npm", "pnpm", "python"]

_KNOWN_MANAGER_VALUES: Final[tuple[ManagerNameLiteral, ...]] = (
    "go",
    "rust",
    "yarn",
    "npm",
    "pnpm",
    "python",
)

VALID_MANAGERS: Final[frozenset[ManagerNameLiteral]] = frozenset(_KNOWN_MANAGER_VALUES)

_REGISTERED_MANAGERS = {strategy.kind.value for strategy in DEFAULT_STRATEGIES}
if not _REGISTERED_MANAGERS <= set(VALID_MANAGERS):  # pragma: no cover - defensive
    missing_manager_diff = _REGISTERED_MANAGERS - set(VALID_MANAGERS)
    MISSING_MANAGER_KINDS: Final[str] = ", ".join(sorted(missing_manager_diff))
    raise RuntimeError(
        "DEFAULT_STRATEGIES defines manager kinds missing from ManagerNameLiteral: "
        f"{MISSING_MANAGER_KINDS}. Update src/pyqa/cli/update.py."
    )


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
    options: Annotated[UpdateOptions, Depends(build_update_options)],
) -> None:
    """Execute dependency updates across discovered workspaces.

    Args:
        options: Parsed CLI options controlling update execution.

    """

    if click.get_current_context().invoked_subcommand:
        return

    _run_update(options)


def _run_update(options: UpdateOptions) -> None:
    """Run the update workflow for the provided CLI options.

    Args:
        options: Parsed CLI options controlling update execution.

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


def _normalise_cli_managers(
    values: list[str] | None,
    use_emoji: bool,
) -> set[ManagerNameLiteral] | None:
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
        valid = ", ".join(sorted(VALID_MANAGERS))
        message = f"Unknown manager(s): {', '.join(invalid)}. Valid managers: {valid}"
        fail(message, use_emoji=use_emoji)
        raise typer.Exit(code=1)
    return {cast(ManagerNameLiteral, value) for value in normalized}


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
) -> set[ManagerNameLiteral] | None:
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


def _normalise_config_managers(
    values: Sequence[str] | None,
    use_emoji: bool,
) -> set[ManagerNameLiteral] | None:
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
    return {cast(ManagerNameLiteral, value) for value in normalized}


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
