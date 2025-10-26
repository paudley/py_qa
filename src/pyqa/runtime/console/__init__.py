# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Console utilities for runtime output."""

from __future__ import annotations

from pyqa.interfaces.core import ConsoleManager

from .manager import RichConsoleManager, console_manager, is_tty

__all__ = ["ConsoleManager", "RichConsoleManager", "console_manager", "is_tty"]
