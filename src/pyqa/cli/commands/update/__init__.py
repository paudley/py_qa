# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Update CLI command package."""

from __future__ import annotations

from typer import Typer

from .command import update_app

__all__ = ["register"]


def register(app: Typer) -> None:
    """Attach update subcommands to ``app``.

    Args:
        app: Typer application receiving the update command group.
    """

    app.add_typer(update_app, name="update")
