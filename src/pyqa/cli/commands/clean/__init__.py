# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Clean CLI command package."""

from __future__ import annotations

from typer import Typer

from .command import clean_app

__all__ = ["register"]


def register(app: Typer) -> None:
    """Register clean subcommands on the provided Typer application.

    Args:
        app: Typer application receiving the clean command group.
    """

    app.add_typer(clean_app, name="sparkly-clean")
