# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Rich console management utilities."""

from __future__ import annotations

import sys
from typing import Literal

from rich.console import Console


def is_tty() -> bool:
    """Return ``True`` when stdout appears to be a TTY."""

    try:
        return sys.stdout.isatty()
    except (AttributeError, ValueError):
        return False


class ConsoleManager:
    """Provide cached ``Console`` instances with consistent settings."""

    def __init__(self) -> None:
        self._cache: dict[tuple[bool, bool], Console] = {}

    def get(self, *, color: bool, emoji: bool) -> Console:
        """Return a configured ``Console`` instance."""

        key = (color, emoji)
        if key not in self._cache:
            tty = is_tty()
            color_system: Literal["auto", "standard", "256", "truecolor", "windows"] | None
            color_system = "auto" if color and tty else None
            self._cache[key] = Console(
                color_system=color_system,
                force_terminal=tty,
                no_color=not (color and tty),
                emoji=emoji,
                soft_wrap=True,
            )
        return self._cache[key]

    def __call__(self, *, color: bool, emoji: bool) -> Console:
        """Expose ``ConsoleManager`` as a callable proxy to :meth:`get`."""

        return self.get(color=color, emoji=emoji)


console_manager = ConsoleManager()


__all__ = ["ConsoleManager", "console_manager", "is_tty"]
