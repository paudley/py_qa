# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Data structures for the install CLI command."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import typer

from ...core.options import InstallOptions

ROOT_OPTION = Annotated[
    Path,
    typer.Option(Path.cwd(), "--root", "-r", help="Project root to bootstrap."),
]
INCLUDE_OPTION = Annotated[
    bool,
    typer.Option(
        True,
        "--include-optional/--no-include-optional",
        help="Install optional typing stubs when runtime packages are present.",
    ),
]
GENERATE_STUBS_OPTION = Annotated[
    bool,
    typer.Option(
        True,
        "--generate-stubs/--no-generate-stubs",
        help="Generate stub skeletons for installed runtime packages.",
    ),
]
EMOJI_OPTION = Annotated[
    bool,
    typer.Option(True, "--emoji/--no-emoji", help="Toggle emoji in CLI output."),
]


@dataclass(slots=True)
class InstallCLIOptions:
    """Normalised CLI inputs for the install command."""

    root: Path
    install: InstallOptions
    use_emoji: bool


def build_install_options(
    root: ROOT_OPTION,
    include_optional: INCLUDE_OPTION,
    generate_stubs: GENERATE_STUBS_OPTION,
    emoji: EMOJI_OPTION,
) -> InstallCLIOptions:
    """Construct ``InstallCLIOptions`` from Typer parameters.

    Args:
        root: Project root supplied via CLI options.
        include_optional: Flag indicating whether optional stubs should be installed.
        generate_stubs: Flag indicating whether stub generation is enabled.
        emoji: Flag controlling emoji usage in logging output.

    Returns:
        InstallCLIOptions: Normalised install command options.
    """

    return InstallCLIOptions(
        root=root.resolve(),
        install=InstallOptions(
            include_optional=include_optional,
            generate_stubs=generate_stubs,
        ),
        use_emoji=emoji,
    )


__all__ = [
    "InstallCLIOptions",
    "build_install_options",
]
