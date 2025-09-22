# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""User-facing logging helpers with optional colour and emoji support."""

from __future__ import annotations

import sys

ANSI = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "blue": "\033[34;1m",
    "cyan": "\033[36;1m",
    "red": "\033[31;1m",
    "green": "\033[32;1m",
    "yellow": "\033[33;1m",
}


def is_tty() -> bool:
    """Return ``True`` when stdout appears to be a TTY."""

    try:
        return sys.stdout.isatty()
    except (AttributeError, ValueError):  # pragma: no cover - defensive
        return False


def colorize(text: str, code: str, enable: bool) -> str:
    """Wrap ``text`` in ANSI colour codes when *enable* is truthy."""

    if not enable or not is_tty():
        return text
    return f"{ANSI.get(code, '')}{text}{ANSI['reset']}"


def emoji(symbol: str, enable: bool) -> str:
    """Return *symbol* when emoji output is enabled, otherwise blank."""

    return symbol if enable else ""


def section(title: str, *, use_color: bool) -> None:
    """Print a section header."""

    print(
        f"\n{colorize('───', 'blue', use_color)} "
        f"{colorize(title, 'cyan', use_color)} "
        f"{colorize('───', 'blue', use_color)}"
    )


def info(msg: str, *, use_emoji: bool) -> None:
    """Emit an informational message."""

    print(f"{emoji('ℹ️ ', use_emoji)}{msg}")


def ok(msg: str, *, use_emoji: bool) -> None:
    """Emit a success message."""

    print(f"{emoji('✅ ', use_emoji)}{msg}")


def warn(msg: str, *, use_emoji: bool) -> None:
    """Emit a warning message."""

    print(f"{emoji('⚠️ ', use_emoji)}{msg}")


def fail(msg: str, *, use_emoji: bool) -> None:
    """Emit an error message."""

    print(f"{emoji('❌ ', use_emoji)}{msg}")
