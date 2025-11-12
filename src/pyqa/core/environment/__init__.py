# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Environment detection helpers."""

from __future__ import annotations

from .virtualenv import (
    NODE_ENV_DEFAULTS,
    WINDOWS_OS_NAME,
    find_venv_bin,
    inject_node_defaults,
    prepend_venv_to_path,
)

__all__ = [
    "NODE_ENV_DEFAULTS",
    "WINDOWS_OS_NAME",
    "find_venv_bin",
    "inject_node_defaults",
    "prepend_venv_to_path",
]
