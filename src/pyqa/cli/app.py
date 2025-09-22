"""Typer application wiring for pyqa."""

from __future__ import annotations

import typer

from .install import install_command
from .lint import lint_command

app = typer.Typer(help="Polyglot lint orchestrator.")
app.command("lint")(lint_command)
app.command("install")(install_command)

__all__ = ["app"]
