# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Typer application wiring for pyqa."""

from __future__ import annotations

import typer

from .banned import check_banned_words
from .clean import clean_app
from .config_cmd import config_app
from .hooks import hooks_app
from .install import install_command
from .lint import lint_command
from .quality import quality_app
from .security import security_scan_command
from .update import update_app

app = typer.Typer(help="Polyglot lint orchestrator.")
app.command("lint")(lint_command)
app.command("install")(install_command)
app.add_typer(config_app, name="config")
app.command("security-scan")(security_scan_command)
app.command("check-banned-words")(check_banned_words)
app.add_typer(quality_app, name="check-quality")
app.add_typer(update_app, name="update")
app.add_typer(clean_app, name="sparkly-clean")
app.add_typer(hooks_app, name="install-hooks")

__all__ = ["app"]
