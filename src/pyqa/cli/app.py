# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Typer application wiring for pyqa."""

from __future__ import annotations

import typer

from .banned import check_banned_words
from .config_cmd import config_app
from .security import security_scan_command
from .install import install_command
from .lint import lint_command
from .quality import quality_app

app = typer.Typer(help="Polyglot lint orchestrator.")
app.command("lint")(lint_command)
app.command("install")(install_command)
app.add_typer(config_app, name="config")
app.command("security-scan")(security_scan_command)
app.command("check-banned-words")(check_banned_words)
app.add_typer(quality_app, name="check-quality")

__all__ = ["app"]
