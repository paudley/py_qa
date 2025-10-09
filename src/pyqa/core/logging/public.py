# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""User-facing logging helpers with optional colour and emoji support."""

from __future__ import annotations

from rich.rule import Rule
from rich.text import Text

from pyqa.interfaces.core import detect_tty, get_console_manager

ANSI = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "blue": "\033[34;1m",
    "cyan": "\033[36;1m",
    "red": "\033[31;1m",
    "green": "\033[32;1m",
    "yellow": "\033[33;1m",
    "white": "\033[37;1m",
    "orange": "\033[38;5;208m",
}


def colorize(text: str, code: str, enable: bool) -> str:
    """Wrap ``text`` in ANSI colour codes when *enable* is truthy."""
    if not enable or not detect_tty():
        return text
    if code.startswith("ansi256:"):
        try:
            value = int(code.split(":", 1)[1])
        except ValueError:
            return text
        return f"\033[38;5;{value}m{text}{ANSI['reset']}"
    return f"{ANSI.get(code, '')}{text}{ANSI['reset']}"


def emoji(symbol: str, enable: bool) -> str:
    """Return *symbol* when emoji output is enabled, otherwise blank."""
    return symbol if enable else ""


def _print_line(
    msg: str,
    *,
    style: str | None,
    use_emoji: bool,
    use_color: bool | None = None,
) -> None:
    color_enabled = detect_tty() if use_color is None else use_color
    console = get_console_manager().get(color=color_enabled, emoji=use_emoji)
    text = Text(msg)
    if style and color_enabled:
        text.stylize(style)
    console.print(text)


def section(title: str, *, use_color: bool) -> None:
    """Print a section header."""
    console = get_console_manager().get(color=use_color, emoji=True)
    if use_color:
        console.print()
        console.print(Rule(title))
    else:
        console.print(f"\n--- {title} ---")


def info(msg: str, *, use_emoji: bool, use_color: bool | None = None) -> None:
    """Emit an informational message."""
    prefix = emoji("ℹ️ ", use_emoji)
    _print_line(f"{prefix}{msg}", style="cyan", use_emoji=use_emoji, use_color=use_color)


def ok(msg: str, *, use_emoji: bool, use_color: bool | None = None) -> None:
    """Emit a success message."""
    prefix = emoji("✅ ", use_emoji)
    _print_line(f"{prefix}{msg}", style="green", use_emoji=use_emoji, use_color=use_color)


def warn(msg: str, *, use_emoji: bool, use_color: bool | None = None) -> None:
    """Emit a warning message."""
    prefix = emoji("⚠️ ", use_emoji)
    _print_line(f"{prefix}{msg}", style="yellow", use_emoji=use_emoji, use_color=use_color)


def fail(msg: str, *, use_emoji: bool, use_color: bool | None = None) -> None:
    """Emit an error message."""
    prefix = emoji("❌ ", use_emoji)
    _print_line(f"{prefix}{msg}", style="red", use_emoji=use_emoji, use_color=use_color)
