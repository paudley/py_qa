# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""CLI command for checking commit messages against banned words."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from ..banned import BannedWordChecker

banned_app = typer.Typer(
    name="check-banned-words", help="Check text for banned words or phrases."
)


@banned_app.command()
def check_banned_words(
    commit_messages_file: Optional[Path] = typer.Argument(
        None, metavar="[FILE]", help="Commit message file to scan."
    ),
    text: Optional[str] = typer.Option(
        None, "--text", help="Text content to scan directly."
    ),
    root: Path = typer.Option(Path.cwd(), "--root", "-r", help="Repository root."),
    personal_list: Optional[Path] = typer.Option(
        None, "--personal-list", help="Override personal banned words list."
    ),
    repo_list: Optional[Path] = typer.Option(
        None, "--repo-list", help="Override repository banned words list."
    ),
) -> None:
    """Scan commit message text for banned words or phrases."""

    if commit_messages_file is None and text is None:
        raise typer.BadParameter("Provide either a commit messages file or --text.")

    lines: list[str]
    if text is not None:
        lines = text.splitlines()
    else:
        file_path = commit_messages_file.expanduser().resolve()
        if not file_path.is_file():
            raise typer.BadParameter(f"Commit messages file not found: {file_path}")
        lines = file_path.read_text(encoding="utf-8").splitlines()

    checker = BannedWordChecker(
        root=root.resolve(),
        personal_list=personal_list,
        repo_list=repo_list,
    )
    matches = checker.scan(lines)

    if not matches:
        typer.echo("✅ No banned words found")
        raise typer.Exit(code=0)

    typer.echo("❌ Banned words/phrases detected:")
    seen: set[str] = set()
    for match in matches:
        if match in seen:
            continue
        seen.add(match)
        typer.echo(f"  • {match}")
    raise typer.Exit(code=1)
