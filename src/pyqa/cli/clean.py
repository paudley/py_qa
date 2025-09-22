# SPDX-License-Identifier: MIT
"""CLI command for sparkling clean cleanup."""

from __future__ import annotations

from pathlib import Path
from typing import List

import typer

from ..clean import sparkly_clean
from ..config_loader import ConfigError, ConfigLoader
from ..logging import fail, warn

clean_app = typer.Typer(
    name="sparkly-clean", help="Remove temporary build/cache artefacts."
)


@clean_app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    root: Path = typer.Option(Path.cwd(), "--root", "-r", help="Project root."),
    pattern: List[str] = typer.Option(  # type: ignore[assignment]
        None,
        "--pattern",
        "-p",
        help="Additional glob pattern to remove (can be repeated).",
    ),
    include_tree: List[str] = typer.Option(
        None,
        "--tree",
        help="Additional directory to clean recursively (can be repeated).",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be removed."
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

    config = load_result.config.clean
    extra_patterns = tuple(pattern or [])
    extra_trees = tuple(include_tree or [])

    result = sparkly_clean(
        root,
        config=config,
        extra_patterns=extra_patterns,
        extra_trees=extra_trees,
        dry_run=dry_run,
    )

    if dry_run:
        for path in sorted(result.skipped):
            warn(f"DRY RUN: would remove {path}", use_emoji=emoji)
    raise typer.Exit(code=0)


__all__ = ["clean_app"]
