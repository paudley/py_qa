# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Banned words CLI command package."""

from __future__ import annotations

from pyqa.cli.protocols import TyperLike

from ...core.shared import register_command
from .command import check_banned_words

__all__ = ["register"]


def register(app: TyperLike) -> None:
    """Register the banned words command.

    Args:
        app: Typer-compatible application receiving the banned words command registration.
    """

    register_command(app, check_banned_words, name="check-banned-words")
