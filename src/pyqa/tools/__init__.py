# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Lazy export surface for tool definitions and registry helpers."""

from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "DEFAULT_REGISTRY",
    "CommandBuilder",
    "DeferredCommand",
    "Parser",
    "Tool",
    "ToolAction",
    "ToolContext",
    "ToolRegistry",
    "register_tool",
]

_LAZY_IMPORTS = {
    "CommandBuilder": "pyqa.tools.base",
    "DeferredCommand": "pyqa.tools.base",
    "Parser": "pyqa.tools.base",
    "Tool": "pyqa.tools.base",
    "ToolAction": "pyqa.tools.base",
    "ToolContext": "pyqa.tools.base",
    "DEFAULT_REGISTRY": "pyqa.tools.registry",
    "ToolRegistry": "pyqa.tools.registry",
    "register_tool": "pyqa.tools.registry",
}


def __getattr__(name: str) -> Any:
    """Lazily import exports to avoid circular import chains."""

    module_name = _LAZY_IMPORTS.get(name)
    if module_name is None:
        raise AttributeError(name) from None
    module = import_module(module_name)
    value = getattr(module, name)
    globals()[name] = value
    return value
