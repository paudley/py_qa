# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Configuration CLI commands."""

from __future__ import annotations

from pyqa.cli.protocols import TyperLike

from .command import config_app

__all__ = ["register"]


def register(app: TyperLike) -> None:
    """Register configuration subcommands on the CLI application.

    Args:
        app: Typer-compatible application receiving the configuration command group.
    """

    app.add_typer(config_app, name="config")
