# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Rich console management utilities."""

from __future__ import annotations

import sys
from typing import Literal

from rich.console import Console

from pyqa.cache.in_memory import memoize
from pyqa.interfaces.core import ConsoleManager


def detect_tty() -> bool:
    """Return ``True`` when stdout appears to be backed by a terminal.

    Returns:
        bool: ``True`` when ``sys.stdout`` reports TTY support, ``False`` otherwise.
    """

    try:
        return sys.stdout.isatty()
    except (AttributeError, ValueError):
        return False


class RichConsoleManager(ConsoleManager):
    """Provision Rich :class:`Console` instances keyed by colour and emoji settings."""

    def __init__(self) -> None:
        """Initialise the manager with an in-memory cache keyed by presentation flags."""

        self._cache: dict[tuple[bool, bool, bool], Console] = {}

    @property
    def managed_presets(self) -> tuple[bool, bool]:
        """Return the default ``(color, emoji)`` tuple managed by the service.

        Returns:
            tuple[bool, bool]: Default preset enabling both colour and emoji output.
        """

        return True, True

    def get(self, *, color: bool, emoji: bool) -> Console:
        """Return a Rich console configured for ``color`` and ``emoji`` preferences.

        Args:
            color: ``True`` when ANSI colour output should be enabled.
            emoji: ``True`` when Rich should render emoji glyphs.

        Returns:
            Console: Cached or newly constructed console matching the preferences.
        """

        tty = detect_tty()
        key = (color, emoji, tty)
        if key not in self._cache:
            color_system: Literal["auto", "standard", "256", "truecolor", "windows"] | None = (
                "auto" if color and tty else None
            )
            self._cache[key] = Console(
                color_system=color_system,
                force_terminal=tty,
                no_color=not (color and tty),
                emoji=emoji,
                soft_wrap=True,
            )
        return self._cache[key]

    def __call__(self, *, color: bool, emoji: bool) -> Console:
        """Return a console to satisfy :class:`ConsoleFactory` semantics.

        Args:
            color: ``True`` when ANSI colour output should be enabled.
            emoji: ``True`` when Rich should render emoji glyphs.

        Returns:
            Console: Console configured with the requested presentation flags.
        """

        return self.get(color=color, emoji=emoji)


@memoize(maxsize=1)
def get_console_manager() -> RichConsoleManager:
    """Return a cached :class:`RichConsoleManager` instance.

    Returns:
        RichConsoleManager: Singleton console manager bound to the process.
    """

    return RichConsoleManager()


def console_manager() -> RichConsoleManager:
    """Return the cached :class:`RichConsoleManager` instance.

    Returns:
        RichConsoleManager: Singleton console manager bound to the process.
    """

    return get_console_manager()


def is_tty() -> bool:
    """Return ``True`` when the current stdout stream is a TTY.

    Returns:
        bool: ``True`` when ``sys.stdout`` resolves to a TTY device.
    """

    return detect_tty()


__all__ = [
    "RichConsoleManager",
    "console_manager",
    "detect_tty",
    "get_console_manager",
    "is_tty",
]
