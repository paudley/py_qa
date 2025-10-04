# SPDX-License-Identifier: MIT
"""Helper services used by the git hooks CLI command."""

from __future__ import annotations

from ..hooks import InstallResult, install_hooks
from ._hooks_cli_models import HookCLIOptions
from .shared import CLIError, CLILogger


def perform_installation(options: HookCLIOptions, *, logger: CLILogger) -> InstallResult:
    """Install hooks for the provided options.

    Args:
        options: Normalized CLI options containing paths and runtime flags.
        logger: Logger used to emit user-facing messages.

    Returns:
        The result reported by :func:`install_hooks`.

    Raises:
        CLIError: Raised when the target repository cannot be located.
    """

    try:
        return install_hooks(
            options.root,
            hooks_dir=options.hooks_dir,
            dry_run=options.dry_run,
        )
    except FileNotFoundError as exc:  # pragma: no cover - CLI path
        logger.fail(str(exc))
        raise CLIError(str(exc)) from exc


def emit_hooks_summary(
    result: InstallResult,
    options: HookCLIOptions,
    *,
    logger: CLILogger,
) -> None:
    """Emit summary warnings after attempting hook installation.

    Args:
        result: The installation result from :func:`perform_installation`.
        options: CLI options controlling dry-run behaviour and emoji output.
        logger: Logger used to display summary warnings.

    """

    if result.backups:
        backup_paths = ", ".join(str(path) for path in result.backups)
        logger.warn(f"Backed up existing hooks: {backup_paths}")
    if options.dry_run and result.installed:
        planned = ", ".join(str(path) for path in result.installed)
        logger.warn(f"DRY RUN: would install {planned}")


__all__ = [
    "emit_hooks_summary",
    "perform_installation",
    "HookCLIOptions",
]
