# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Git hooks CLI command package."""

from __future__ import annotations

from typer import Typer

from .command import hooks_app

__all__ = ["register"]


def register(app: Typer) -> None:
    """Register Git hook subcommands on the Typer application.

    Args:
        app: Typer application receiving the hooks command group.
    """

    app.add_typer(hooks_app, name="install-hooks")
