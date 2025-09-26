# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Tool registry providing discovery by name or language."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Iterator, Mapping

from .base import Tool


class ToolRegistry(Mapping[str, Tool]):
    """Central registry for tool definitions.

    ``ToolRegistry`` behaves like a read-only mapping whose keys are tool names
    and whose values are :class:`Tool` instances. It also exposes helpers for
    discovering tools by language and registering new adapters.
    """

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}
        self._by_language: dict[str, set[str]] = defaultdict(set)

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' already registered")
        self._tools[tool.name] = tool
        for language in tool.languages:
            self._by_language[language].add(tool.name)

    def get(self, name: str) -> Tool:
        return self._tools[name]

    def try_get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def tools(self) -> Iterable[Tool]:
        """Return an iterable of all registered tools."""
        return self._tools.values()

    def tools_for_language(self, language: str) -> Iterable[Tool]:
        """Yield tools associated with *language*."""
        names = self._by_language.get(language, set())
        return (self._tools[name] for name in names)

    def __contains__(self, name: object) -> bool:  # type: ignore[override]
        return isinstance(name, str) and name in self._tools

    def __len__(self) -> int:
        return len(self._tools)

    def __iter__(self) -> Iterator[str]:
        return iter(self._tools)

    def __getitem__(self, name: str) -> Tool:
        return self._tools[name]

    def keys(self) -> Iterable[str]:
        """Return an iterable of registered tool names."""
        return self._tools.keys()

    def values(self) -> Iterable[Tool]:  # type: ignore[override]
        """Return an iterable of registered :class:`Tool` objects."""
        return self._tools.values()

    def items(self) -> Iterable[tuple[str, Tool]]:  # type: ignore[override]
        """Return an iterable of ``(name, tool)`` pairs."""
        return self._tools.items()


DEFAULT_REGISTRY = ToolRegistry()


def register_tool(tool: Tool) -> None:
    """Convenience helper mirroring the legacy global registration."""
    DEFAULT_REGISTRY.register(tool)
