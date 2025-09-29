# SPDX-License-Identifier: MIT
# Legacy builtins module exposing installer helpers and registry wiring.

from __future__ import annotations

from .builtin_registry import initialize_registry, register_catalog_tools

__all__ = [
    "initialize_registry",
    "register_catalog_tools",
]
