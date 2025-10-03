# SPDX-License-Identifier: MIT
"""Data structures for the git hooks CLI command."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Final

import typer

from .shared import Depends

DEFAULT_HOOKS_DIR: Final[Path] = Path(".git/hooks")

ROOT_OPTION = Annotated[
    Path,
    typer.Option(Path.cwd(), "--root", "-r", help="Repository root."),
]
HOOKS_DIR_OPTION = Annotated[
    Path,
    typer.Option(
        DEFAULT_HOOKS_DIR,
        "--hooks-dir",
        help="Overrides the hooks directory.",
    ),
]
DRY_RUN_OPTION = Annotated[
    bool,
    typer.Option(False, "--dry-run", help="Show actions without modifying files."),
]
EMOJI_OPTION = Annotated[
    bool,
    typer.Option(True, "--emoji/--no-emoji", help="Toggle emoji output."),
]


@dataclass(slots=True)
class HookCLIOptions:
    """Capture CLI options for hook installation."""

    root: Path
    hooks_dir: Path | None
    dry_run: bool
    emoji: bool

    @classmethod
    def from_cli(
        cls,
        root: Path,
        hooks_dir: Path,
        *,
        dry_run: bool,
        emoji: bool,
    ) -> "HookCLIOptions":
        """Return options parsed from CLI arguments."""

        resolved_root = root.resolve()
        override = hooks_dir if hooks_dir != DEFAULT_HOOKS_DIR else None
        return cls(
            root=resolved_root,
            hooks_dir=override.resolve() if override is not None else None,
            dry_run=dry_run,
            emoji=emoji,
        )


def build_hook_options(
    root: ROOT_OPTION,
    hooks_dir: HOOKS_DIR_OPTION,
    dry_run: DRY_RUN_OPTION,
    emoji: EMOJI_OPTION,
) -> HookCLIOptions:
    """Construct ``HookCLIOptions`` from Typer callback parameters."""

    return HookCLIOptions.from_cli(
        root=root,
        hooks_dir=hooks_dir,
        dry_run=dry_run,
        emoji=emoji,
    )


__all__ = [
    "Depends",
    "DEFAULT_HOOKS_DIR",
    "ROOT_OPTION",
    "HOOKS_DIR_OPTION",
    "DRY_RUN_OPTION",
    "EMOJI_OPTION",
    "HookCLIOptions",
    "build_hook_options",
]
