"""Typer application wiring for pyqa."""

from __future__ import annotations

import typer

from .config_cmd import config_app
from .install import install_command
from .lint import lint_command

app = typer.Typer(help="Polyglot lint orchestrator.")
app.command("lint")(lint_command)
app.command("install")(install_command)
app.add_typer(config_app, name="config")

__all__ = ["app"]
