# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Shared data structures for the sparkly-clean CLI."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import typer

from .shared import Depends

ROOT_OPTION = Annotated[
    Path,
    typer.Option(Path.cwd(), "--root", "-r", help="Project root."),
]
PATTERN_OPTION = Annotated[
    list[str] | None,
    typer.Option(
        None,
        "--pattern",
        "-p",
        help="Additional glob pattern to remove (repeatable).",
    ),
]
TREE_OPTION = Annotated[
    list[str] | None,
    typer.Option(
        None,
        "--tree",
        help="Additional directory to clean recursively (repeatable).",
    ),
]
DRY_RUN_OPTION = Annotated[
    bool,
    typer.Option(False, "--dry-run", help="Show what would be removed."),
]
EMOJI_OPTION = Annotated[
    bool,
    typer.Option(True, "--emoji/--no-emoji", help="Toggle emoji output."),
]


def normalize_cli_values(values: Sequence[str] | None) -> tuple[str, ...]:
    """Return sanitized CLI values preserving order."""

    if not values:
        return ()
    cleaned_values: list[str] = []
    for entry in values:
        if not entry:
            continue
        stripped = entry.strip()
        if stripped:
            cleaned_values.append(stripped)
    return tuple(cleaned_values)


@dataclass(slots=True)
class CleanCLIOptions:
    """Capture CLI overrides supplied to the sparkly-clean command."""

    root: Path
    extra_patterns: tuple[str, ...]
    extra_trees: tuple[str, ...]
    dry_run: bool
    emoji: bool


def _build_clean_path_options(
    pattern: PATTERN_OPTION,
    include_tree: TREE_OPTION,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Normalise pattern and tree option values."""

    return normalize_cli_values(pattern), normalize_cli_values(include_tree)


def build_clean_options(
    root: ROOT_OPTION,
    path_args: Annotated[
        tuple[tuple[str, ...], tuple[str, ...]],
        Depends(_build_clean_path_options),
    ],
    dry_run: DRY_RUN_OPTION,
    emoji: EMOJI_OPTION,
) -> CleanCLIOptions:
    """Construct ``CleanCLIOptions`` from Typer callback parameters."""

    patterns, trees = path_args
    return CleanCLIOptions(
        root=root.resolve(),
        extra_patterns=patterns,
        extra_trees=trees,
        dry_run=dry_run,
        emoji=emoji,
    )


__all__ = [
    "Depends",
    "ROOT_OPTION",
    "PATTERN_OPTION",
    "TREE_OPTION",
    "DRY_RUN_OPTION",
    "EMOJI_OPTION",
    "CleanCLIOptions",
    "normalize_cli_values",
    "_build_clean_path_options",
    "build_clean_options",
]
