# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""CLI command for checking commit messages against banned words."""

from __future__ import annotations

from typing import Annotated

import typer

from ....banned import BannedWordChecker
from ...core.shared import Depends
from ...core.typer_ext import create_typer
from .models import BannedCLIOptions, build_banned_options

banned_app = create_typer(name="check-banned-words", help="Check text for banned words or phrases.")


@banned_app.command()
def check_banned_words(
    options: Annotated[BannedCLIOptions, Depends(build_banned_options)],
) -> None:
    """Scan commit message text for banned words or phrases.

    Args:
        options: Structured CLI options containing scan settings.

    Raises:
        typer.BadParameter: If neither text input nor commit messages file is provided.
        typer.Exit: Raised with an appropriate exit status after scanning.
    """
    text = options.text
    commit_messages_file = options.message_file
    if text is None and commit_messages_file is None:
        raise typer.BadParameter("Provide either a commit messages file or --text.")

    lines: list[str]
    if text is not None:
        lines = text.splitlines()
    else:
        file_path = commit_messages_file
        if file_path is None or not file_path.is_file():
            raise typer.BadParameter("Commit messages file not found or unreadable")
        lines = file_path.read_text(encoding="utf-8").splitlines()

    checker = BannedWordChecker(
        root=options.root,
        personal_list=options.personal_list,
        repo_list=options.repo_list,
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
