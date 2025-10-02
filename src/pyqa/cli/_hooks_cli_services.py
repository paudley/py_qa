# SPDX-License-Identifier: MIT
"""Helper services used by the git hooks CLI command."""

from __future__ import annotations

import typer

from ..hooks import InstallResult, install_hooks
from ..logging import fail, warn
from ._hooks_cli_models import HookCLIOptions


def perform_installation(options: HookCLIOptions) -> InstallResult:
    """Install hooks for the provided options.

    Args:
        options: Normalized CLI options containing paths and runtime flags.

    Returns:
        The result reported by :func:`install_hooks`.

    Raises:
        typer.Exit: Raised when the target repository cannot be located. The
            error message is emitted via :func:`fail` before exiting.
    """

    try:
        return install_hooks(
            options.root,
            hooks_dir=options.hooks_dir,
            dry_run=options.dry_run,
        )
    except FileNotFoundError as exc:  # pragma: no cover - CLI path
        fail(str(exc), use_emoji=options.emoji)
        raise typer.Exit(code=1) from exc


def emit_hooks_summary(result: InstallResult, options: HookCLIOptions) -> None:
    """Emit summary warnings after attempting hook installation.

    Args:
        result: The installation result from :func:`perform_installation`.
        options: CLI options controlling dry-run behaviour and emoji output.

    Returns:
        None. The function performs logging side effects only.
    """

    if result.backups:
        backup_paths = ", ".join(str(path) for path in result.backups)
        warn(f"Backed up existing hooks: {backup_paths}", use_emoji=options.emoji)
    if options.dry_run and result.installed:
        planned = ", ".join(str(path) for path in result.installed)
        warn(f"DRY RUN: would install {planned}", use_emoji=options.emoji)


__all__ = [
    "emit_hooks_summary",
    "perform_installation",
    "HookCLIOptions",
]
