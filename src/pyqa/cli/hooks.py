# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""CLI command for installing git hooks."""

from __future__ import annotations

from pathlib import Path

import typer

from ..hooks import install_hooks
from ..logging import fail

hooks_app = typer.Typer(
    name="install-hooks",
    help="Install py-qa git hooks (pre-commit, pre-push, commit-msg).",
)


@hooks_app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    root: Path = typer.Option(Path.cwd(), "--root", "-r", help="Repository root."),
    hooks_dir: Path = typer.Option(Path(".git/hooks"), "--hooks-dir", help="Overrides the hooks directory."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show actions without modifying files."),
) -> None:
    if ctx.invoked_subcommand:
        return

    try:
        install_hooks(
            root,
            hooks_dir=hooks_dir if hooks_dir != Path(".git/hooks") else None,
            dry_run=dry_run,
        )
    except FileNotFoundError as exc:
        fail(str(exc), use_emoji=True)
        raise typer.Exit(code=1) from exc
    raise typer.Exit(code=0)


__all__ = ["hooks_app"]
