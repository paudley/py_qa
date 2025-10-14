# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""CLI application entry point wiring commands and shared services."""

from __future__ import annotations

from .commands import register_commands
from .core.typer_ext import TyperAppConfig, create_typer

app = create_typer(config=TyperAppConfig(help_text="Polyglot lint orchestrator."))
register_commands(app)

__all__ = ["app"]
