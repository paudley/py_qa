# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Quality CLI command registration."""

from __future__ import annotations

from typer import Typer

from .command import quality_app

__all__ = ["register"]


def register(app: Typer) -> None:
    """Attach quality sub-commands to the CLI application.

    Args:
        app: Typer application receiving the quality command group.
    """

    app.add_typer(quality_app, name="check-quality")
