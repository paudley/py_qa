# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Lint command package exposing registration helpers."""

from __future__ import annotations

from typer import Typer

from ...core.shared import register_command
from .command import lint_command

__all__ = ["register"]


def register(app: Typer) -> None:
    """Register the lint command with the Typer ``app``.

    Args:
        app: Typer application receiving the lint command registration.
    """

    register_command(app, lint_command, name="lint")
