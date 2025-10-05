# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Typer application wiring for pyqa."""

from __future__ import annotations

from .banned import check_banned_words
from .clean import clean_app
from .config_cmd import config_app
from .hooks import hooks_app
from .install import install_command
from .lint import lint_command
from .quality import quality_app
from .security import security_scan_command
from .shared import register_command
from .tool_info import tool_info_command
from .typer_ext import create_typer
from .update import update_app

app = create_typer(help="Polyglot lint orchestrator.")
register_command(app, lint_command, name="lint")
register_command(app, install_command, name="install")
app.add_typer(config_app, name="config")
register_command(app, security_scan_command, name="security-scan")
register_command(app, check_banned_words, name="check-banned-words")
register_command(app, tool_info_command, name="tool-info")
app.add_typer(quality_app, name="check-quality")
app.add_typer(update_app, name="update")
app.add_typer(clean_app, name="sparkly-clean")
app.add_typer(hooks_app, name="install-hooks")

__all__ = ["app"]
