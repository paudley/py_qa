# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Hook registration and installation services."""

from __future__ import annotations

from .models import InstallResult
from .registry import available_hooks, is_supported, normalise_hook_order
from .runner import install_hooks

HOOK_NAMES: tuple[str, ...] = available_hooks()

__all__ = [
    "available_hooks",
    "is_supported",
    "normalise_hook_order",
    "HOOK_NAMES",
    "InstallResult",
    "install_hooks",
]
