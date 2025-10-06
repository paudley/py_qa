# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Install CLI command."""

from __future__ import annotations

from typer import Typer

from ...core.shared import register_command
from .command import install_command

__all__ = ["register"]


def register(app: Typer) -> None:
    """Register the install command with ``app``.

    Args:
        app: Typer application receiving the install command registration.
    """

    register_command(app, install_command, name="install")
