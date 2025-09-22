# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Security scan CLI command."""

from __future__ import annotations

from pathlib import Path
from typing import List

import typer

from ..security import SecurityScanner, get_staged_files


def security_scan_command(
    files: List[Path] | None = typer.Argument(
        None, metavar="[FILES...]", help="Specific files to scan."
    ),
    root: Path = typer.Option(Path.cwd(), "--root", "-r", help="Project root."),
    staged: bool = typer.Option(
        True,
        "--staged/--no-staged",
        help="Include staged files when no explicit files are provided.",
    ),
    no_bandit: bool = typer.Option(
        False, "--no-bandit", help="Skip running bandit static analysis."
    ),
    no_emoji: bool = typer.Option(False, "--no-emoji", help="Disable emoji in output."),
) -> None:
    """Run security scans across the project."""

    root = root.resolve()
    selected_files = list(files or [])
    if not selected_files and staged:
        selected_files = get_staged_files(root)

    if not selected_files:
        typer.echo("No files to scan.")
        raise typer.Exit(code=0)

    scanner = SecurityScanner(
        root=root,
        use_emoji=not no_emoji,
        use_bandit=not no_bandit,
    )
    result = scanner.run(selected_files)

    if result.secret_files or result.pii_files or result.temp_files:
        typer.echo("")
    for path, matches in result.secret_files.items():
        typer.echo(f"❌ {path}")
        for match in matches:
            typer.echo(f"    {match}")
    for path, matches in result.pii_files.items():
        typer.echo(f"⚠️  Potential PII in {path}")
        for match in matches:
            typer.echo(f"    {match}")
    for path in result.temp_files:
        typer.echo(f"⚠️  Temporary/backup file tracked: {path}")

    if result.bandit_issues:
        typer.echo("")
        typer.echo("Bandit summary:")
        for level, count in result.bandit_issues.items():
            typer.echo(f"  {level.split('.')[-1].title()}: {count}")
        if result.bandit_samples:
            typer.echo("  Sample issues:")
            for sample in result.bandit_samples:
                typer.echo(f"    {sample}")

    if result.findings:
        typer.echo("")
        typer.echo(f"❌ Security scan found {result.findings} potential issue(s)")
        raise typer.Exit(code=1)

    typer.echo("✅ No security issues detected")
    raise typer.Exit(code=0)
