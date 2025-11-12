# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Lint command package exposing registration helpers."""

from __future__ import annotations

from pyqa.cli.protocols import TyperLike

from ...core.shared import register_command
from .command import lint_command

__all__ = ["register"]


def register(app: TyperLike) -> None:
    """Register the lint command with the Typer ``app``.

    Args:
        app: Typer-compatible application receiving the lint command registration.
    """

    register_command(app, lint_command, name="lint")
