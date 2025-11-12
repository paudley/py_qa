# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Data structures for the dependency update CLI."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import typer

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
    """Normalised CLI inputs for the update workflow."""

    root: Path
    managers: list[str] | None
    skip_lint_install: bool
    dry_run: bool
    use_emoji: bool


def build_update_options(
    root: ROOT_OPTION,
    manager: MANAGER_OPTION,
    skip_lint_install: SKIP_LINT_OPTION,
    dry_run: DRY_RUN_OPTION,
    emoji: EMOJI_OPTION,
) -> UpdateOptions:
    """Construct ``UpdateOptions`` from Typer parameters.

    Args:
        root: Project root directory supplied via CLI options.
        manager: Optional list of manager names requested by the user.
        skip_lint_install: Flag disabling lint install bootstrapping.
        dry_run: Flag indicating whether commands should be executed.
        emoji: Flag controlling emoji usage in CLI output.

    Returns:
        UpdateOptions: Structured CLI options for dependency updates.
    """

    return UpdateOptions(
        root=root.resolve(),
        managers=manager,
        skip_lint_install=skip_lint_install,
        dry_run=dry_run,
        use_emoji=emoji,
    )


__all__ = [
    "UpdateOptions",
    "build_update_options",
    "ROOT_OPTION",
    "MANAGER_OPTION",
    "SKIP_LINT_OPTION",
    "DRY_RUN_OPTION",
    "EMOJI_OPTION",
]
