# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Hook registration and installation services."""

from __future__ import annotations

from .installer import HOOK_NAMES, install_hooks
from .models import InstallResult

__all__ = [
    "HOOK_NAMES",
    "InstallResult",
    "install_hooks",
]
