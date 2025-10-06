# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Configuration CLI commands."""

from __future__ import annotations

from typer import Typer

from .command import config_app

__all__ = ["register"]


def register(app: Typer) -> None:
    """Attach configuration sub-commands to the CLI application.

    Args:
        app: Typer application receiving the configuration command group.
    """

    app.add_typer(config_app, name="config")
