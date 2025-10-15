# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Doctor CLI command package."""

from __future__ import annotations

from typer import Typer

from ...core.shared import register_command
from .command import doctor_command

__all__ = ["register"]


def register(app: Typer) -> None:
    """Register the doctor diagnostics command on the Typer application.

    Args:
        app: Typer application receiving the doctor command.
    """

    register_command(app, doctor_command, name="doctor")
