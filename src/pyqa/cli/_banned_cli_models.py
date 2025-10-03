# SPDX-License-Identifier: MIT
"""Data structures for the banned words CLI command."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import typer

ROOT_OPTION = Annotated[
    Path,
    typer.Option(Path.cwd(), "--root", "-r", help="Repository root."),
]
TEXT_OPTION = Annotated[
    str | None,
    typer.Option(None, "--text", help="Text content to scan directly."),
]
PERSONAL_LIST_OPTION = Annotated[
    Path | None,
    typer.Option(None, "--personal-list", help="Override personal banned words list."),
]
REPO_LIST_OPTION = Annotated[
    Path | None,
    typer.Option(None, "--repo-list", help="Override repository banned words list."),
]
COMMIT_FILE_ARGUMENT = Annotated[
    Path | None,
    typer.Argument(None, metavar="[FILE]", help="Commit message file to scan."),
]


@dataclass(slots=True)
class BannedCLIOptions:
    """Normalised CLI inputs for the banned words scanner."""

    root: Path
    message_file: Path | None
    text: str | None
    personal_list: Path | None
    repo_list: Path | None


def build_banned_options(
    commit_messages_file: COMMIT_FILE_ARGUMENT,
    text: TEXT_OPTION,
    root: ROOT_OPTION,
    personal_list: PERSONAL_LIST_OPTION,
    repo_list: REPO_LIST_OPTION,
) -> BannedCLIOptions:
    """Construct ``BannedCLIOptions`` from Typer parameters."""

    resolved_root = root.resolve()
    resolved_file = commit_messages_file.expanduser().resolve() if commit_messages_file else None
    return BannedCLIOptions(
        root=resolved_root,
        message_file=resolved_file,
        text=text,
        personal_list=personal_list,
        repo_list=repo_list,
    )


__all__ = [
    "BannedCLIOptions",
    "build_banned_options",
    "COMMIT_FILE_ARGUMENT",
    "TEXT_OPTION",
    "ROOT_OPTION",
    "PERSONAL_LIST_OPTION",
    "REPO_LIST_OPTION",
]
