# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""CLI command for sparkling clean cleanup."""

from __future__ import annotations

from pathlib import Path

import typer

from ..clean import sparkly_clean
from .typer_ext import create_typer
from ._clean_cli_models import CleanCLIOptions
from ._clean_cli_services import (
    emit_dry_run_summary,
    emit_py_qa_warning,
    load_clean_config,
)

clean_app = create_typer(
    name="sparkly-clean",
    help="Remove temporary build/cache artefacts.",
    invoke_without_command=True,
)


@clean_app.callback(invoke_without_command=True)
def main(
    root: Path = typer.Option(Path.cwd(), "--root", "-r", help="Project root."),
    pattern: list[str] | None = typer.Option(
        None,
        "--pattern",
        "-p",
        help="Additional glob pattern to remove (can be repeated).",
    ),
    include_tree: list[str] | None = typer.Option(
        None,
        "--tree",
        help="Additional directory to clean recursively (can be repeated).",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be removed."),
    emoji: bool = typer.Option(True, "--emoji/--no-emoji", help="Toggle emoji output."),
) -> None:
    """Execute the sparkly-clean command.

    Args:
        root: Project root to clean. Defaults to the current working directory.
        pattern: Optional additional glob patterns. Typer yields ``None`` when
            the option is not provided.
        include_tree: Optional directories to clean recursively.
        dry_run: Indicates that removal should be logged but not performed.
        emoji: Enables or disables emoji output across CLI helpers.

    Returns:
        None. The function exits the Typer command with status information.
    """

    root_path = root.resolve()
    options = CleanCLIOptions.from_cli(pattern, include_tree, dry_run=dry_run, emoji=emoji)
    config = load_clean_config(root_path, emoji=options.emoji)

    result = sparkly_clean(
        root_path,
        config=config,
        extra_patterns=options.extra_patterns,
        extra_trees=options.extra_trees,
        dry_run=options.dry_run,
    )

    emit_py_qa_warning(result, root_path, emoji=options.emoji)
    if options.dry_run:
        emit_dry_run_summary(result, emoji=options.emoji)
    raise typer.Exit(code=0)


__all__ = ["clean_app", "CleanCLIOptions"]
