# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Install CLI command."""

from __future__ import annotations

from pyqa.cli.protocols import TyperLike

from ...core.shared import register_command
from .command import install_command

__all__ = ["register"]


def register(app: TyperLike) -> None:
    """Register the install command with ``app``.

    Args:
        app: Typer-compatible application receiving the install command registration.
    """

    register_command(app, install_command, name="install")
