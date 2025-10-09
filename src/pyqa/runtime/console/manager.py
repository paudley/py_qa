# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Rich console management utilities."""

from __future__ import annotations

from pyqa.interfaces.core import RichConsoleManager, detect_tty


def is_tty() -> bool:
    """Return ``True`` when stdout appears to be a TTY."""

    return detect_tty()


class ConsoleManager(RichConsoleManager):
    """Backward-compatible alias for the shared Rich console manager."""


console_manager = ConsoleManager()


__all__ = ["ConsoleManager", "console_manager", "is_tty"]
