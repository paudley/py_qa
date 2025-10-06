# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Tool information CLI command."""

from __future__ import annotations

from typer import Typer

from ...core.shared import register_command
from .command import tool_info_command

__all__ = ["register"]


def register(app: Typer) -> None:
    """Register the tool-info command with ``app``.

    Args:
        app: Typer application receiving the tool-info command registration.
    """

    register_command(app, tool_info_command, name="tool-info")
