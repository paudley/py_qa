# SPDX-License-Identifier: MIT
"""Registry wiring for built-in tool definitions."""

from __future__ import annotations

from collections.abc import Iterable

from .base import Tool
from .builtin_catalog_misc import misc_tools
from .builtin_catalog_python import python_tools
from .registry import DEFAULT_REGISTRY, ToolRegistry


def register_builtin_tools(registry: ToolRegistry | None = None) -> None:
    """Register all built-in tools with the provided *registry*."""
    target = registry or DEFAULT_REGISTRY
    for tool in _iter_all_tools():
        target.register(tool)


def _iter_all_tools() -> Iterable[Tool]:
    yield from python_tools()
    yield from misc_tools()


__all__ = ["register_builtin_tools"]
