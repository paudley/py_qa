"""Tool registry providing discovery by name or language."""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from .base import Tool


class ToolRegistry:
    """Central registry for tool definitions."""

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
        return self._tools.values()

    def tools_for_language(self, language: str) -> Iterable[Tool]:
        names = self._by_language.get(language, set())
        return (self._tools[name] for name in names)

    def __contains__(self, name: str) -> bool:  # pragma: no cover - trivial
        return name in self._tools

    def __len__(self) -> int:  # pragma: no cover - trivial
        return len(self._tools)


DEFAULT_REGISTRY = ToolRegistry()


def register_tool(tool: Tool) -> None:
    """Convenience helper mirroring the legacy global registration."""

    DEFAULT_REGISTRY.register(tool)
