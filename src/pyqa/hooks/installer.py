# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Backwards-compatibility wrappers for hook installation helpers."""

from __future__ import annotations

from .registry import available_hooks
from .runner import install_hooks

HOOK_NAMES: tuple[str, ...] = available_hooks()

__all__ = ["HOOK_NAMES", "install_hooks"]
