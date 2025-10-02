# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""CLI command for installing git hooks."""

from __future__ import annotations

from pathlib import Path

import typer

from .typer_ext import create_typer
from ._hooks_cli_models import DEFAULT_HOOKS_DIR, HookCLIOptions
from ._hooks_cli_services import emit_hooks_summary, perform_installation


hooks_app = create_typer(
    name="install-hooks",
    help="Install py-qa git hooks (pre-commit, pre-push, commit-msg).",
    invoke_without_command=True,
)


@hooks_app.callback(invoke_without_command=True)
def main(
    root: Path = typer.Option(Path.cwd(), "--root", "-r", help="Repository root."),
    hooks_dir: Path = typer.Option(
        DEFAULT_HOOKS_DIR,
        "--hooks-dir",
        help="Overrides the hooks directory.",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show actions without modifying files."),
    emoji: bool = typer.Option(True, "--emoji/--no-emoji", help="Toggle emoji output."),
) -> None:
    """Install py-qa git hooks for the current repository.

    Args:
        root: Repository root provided via the CLI. Defaults to the current
            working directory.
        hooks_dir: Target hooks directory. Defaults to ``.git/hooks``.
        dry_run: Indicates whether operations should be logged only.
        emoji: Enables or disables emoji output for user-facing messages.

    Returns:
        None. The function exits the Typer application with status information.
    """

    options = HookCLIOptions.from_cli(root, hooks_dir, dry_run=dry_run, emoji=emoji)
    result = perform_installation(options)

    emit_hooks_summary(result, options)
    raise typer.Exit(code=0)


__all__ = ["hooks_app", "HookCLIOptions"]
