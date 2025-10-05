# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Data structures for the security scan CLI command."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import typer

FILES_ARGUMENT = Annotated[
    list[Path] | None,
    typer.Argument(
        None,
        metavar="[FILES...]",
        help="Specific files to scan.",
    ),
]
ROOT_OPTION = Annotated[
    Path,
    typer.Option(Path.cwd(), "--root", "-r", help="Project root."),
]
STAGED_OPTION = Annotated[
    bool,
    typer.Option(
        True,
        "--staged/--no-staged",
        help="Include staged files when no explicit files are provided.",
    ),
]
NO_BANDIT_OPTION = Annotated[
    bool,
    typer.Option(False, "--no-bandit", help="Skip running bandit static analysis."),
]
NO_EMOJI_OPTION = Annotated[
    bool,
    typer.Option(False, "--no-emoji", help="Disable emoji in output."),
]


@dataclass(slots=True)
class SecurityCLIOptions:
    """Normalised CLI inputs for the security scan command."""

    root: Path
    files: tuple[Path, ...]
    staged: bool
    use_bandit: bool
    use_emoji: bool


def _normalise_files(paths: list[Path] | None) -> tuple[Path, ...]:
    return tuple(path.expanduser() for path in (paths or []))


def build_security_options(
    files: FILES_ARGUMENT,
    root: ROOT_OPTION,
    staged: STAGED_OPTION,
    no_bandit: NO_BANDIT_OPTION,
    no_emoji: NO_EMOJI_OPTION,
) -> SecurityCLIOptions:
    """Construct ``SecurityCLIOptions`` from Typer parameters."""

    return SecurityCLIOptions(
        root=root.resolve(),
        files=_normalise_files(files),
        staged=staged,
        use_bandit=not no_bandit,
        use_emoji=not no_emoji,
    )


__all__ = [
    "SecurityCLIOptions",
    "build_security_options",
    "FILES_ARGUMENT",
    "ROOT_OPTION",
    "STAGED_OPTION",
    "NO_BANDIT_OPTION",
    "NO_EMOJI_OPTION",
]
