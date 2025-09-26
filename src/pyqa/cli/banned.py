# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""CLI command for checking commit messages against banned words."""

from __future__ import annotations

from pathlib import Path

import typer

from ..banned import BannedWordChecker
from .typer_ext import create_typer

banned_app = create_typer(name="check-banned-words", help="Check text for banned words or phrases.")


@banned_app.command()
def check_banned_words(
    commit_messages_file: Path | None = typer.Argument(
        None,
        metavar="[FILE]",
        help="Commit message file to scan.",
    ),
    text: str | None = typer.Option(None, "--text", help="Text content to scan directly."),
    root: Path = typer.Option(Path.cwd(), "--root", "-r", help="Repository root."),
    personal_list: Path | None = typer.Option(
        None,
        "--personal-list",
        help="Override personal banned words list.",
    ),
    repo_list: Path | None = typer.Option(
        None,
        "--repo-list",
        help="Override repository banned words list.",
    ),
) -> None:
    """Scan commit message text for banned words or phrases."""
    if text is None and commit_messages_file is None:
        raise typer.BadParameter("Provide either a commit messages file or --text.")

    lines: list[str]
    if text is not None:
        lines = text.splitlines()
    else:
        file_path = commit_messages_file.expanduser().resolve() if commit_messages_file else None
        if file_path is None or not file_path.is_file():
            raise typer.BadParameter("Commit messages file not found or unreadable")
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
