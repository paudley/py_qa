# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Tool registry providing discovery by name or language."""

from __future__ import annotations

import heapq
from collections import defaultdict
from collections.abc import Iterable, Iterator, Mapping

from .base import Tool


class ToolRegistry(Mapping[str, Tool]):
    """Central registry for tool definitions.

    ``ToolRegistry`` behaves like a read-only mapping whose keys are tool names
    and whose values are :class:`Tool` instances. It also exposes helpers for
    discovering tools by language and registering new adapters.
    """

    _PHASE_ORDER: tuple[str, ...] = (
        "lint",
        "format",
        "analysis",
        "security",
        "test",
        "coverage",
        "utility",
    )

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}
        self._by_language: dict[str, list[str]] = defaultdict(list)
        self._ordered: tuple[str, ...] = ()

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' already registered")
        self._tools[tool.name] = tool
        self._recompute_order()

    def reset(self) -> None:
        """Remove all tools from the registry."""
        self._tools.clear()
        self._by_language.clear()
        self._ordered = ()

    def get(self, name: str) -> Tool:
        return self._tools[name]

    def try_get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def tools(self) -> Iterable[Tool]:
        """Return an iterable of all registered tools."""
        return tuple(self._tools[name] for name in self._ordered)

    def tools_for_language(self, language: str) -> Iterable[Tool]:
        """Yield tools associated with *language*."""
        names = self._by_language.get(language, [])
        return tuple(self._tools[name] for name in names if name in self._tools)

    def __contains__(self, name: object) -> bool:  # type: ignore[override]
        return isinstance(name, str) and name in self._tools

    def __len__(self) -> int:
        return len(self._tools)

    def __iter__(self) -> Iterator[str]:
        return iter(self._ordered)

    def __getitem__(self, name: str) -> Tool:
        return self._tools[name]

    def keys(self) -> Iterable[str]:
        """Return an iterable of registered tool names."""
        return self._ordered

    def values(self) -> Iterable[Tool]:  # type: ignore[override]
        """Return an iterable of registered :class:`Tool` objects."""
        return tuple(self._tools[name] for name in self._ordered)

    def items(self) -> Iterable[tuple[str, Tool]]:  # type: ignore[override]
        """Return an iterable of ``(name, tool)`` pairs."""
        return tuple((name, self._tools[name]) for name in self._ordered)

    def _recompute_order(self) -> None:
        phase_priority = {phase: index for index, phase in enumerate(self._PHASE_ORDER)}
        grouped: dict[str, list[Tool]] = defaultdict(list)
        for tool in self._tools.values():
            grouped[tool.phase].append(tool)

        ordered: list[str] = []
        for phase in sorted(
            grouped,
            key=lambda candidate: (phase_priority.get(candidate, len(phase_priority)), candidate),
        ):
            ordered.extend(self._order_phase(grouped[phase]))
        self._ordered = tuple(ordered)
        self._rebuild_language_index()

    def _order_phase(self, tools: list[Tool]) -> list[str]:
        adjacency: dict[str, set[str]] = {}
        indegree: dict[str, int] = {}
        names_in_phase = {tool.name for tool in tools}
        for tool in tools:
            adjacency.setdefault(tool.name, set())
            indegree.setdefault(tool.name, 0)

        for tool in tools:
            for successor in tool.before:
                if successor in names_in_phase:
                    adjacency[tool.name].add(successor)
            for predecessor in tool.after:
                if predecessor in names_in_phase:
                    adjacency.setdefault(predecessor, set()).add(tool.name)

        for source, targets in adjacency.items():
            indegree.setdefault(source, 0)
            for target in targets:
                indegree[target] = indegree.get(target, 0) + 1

        ready = [name for name, count in indegree.items() if count == 0]
        heapq.heapify(ready)
        ordered: list[str] = []
        while ready:
            current = heapq.heappop(ready)
            ordered.append(current)
            for neighbor in sorted(adjacency.get(current, ())):
                indegree[neighbor] -= 1
                if indegree[neighbor] == 0:
                    heapq.heappush(ready, neighbor)

        if len(ordered) != len(names_in_phase):
            remaining = sorted(names_in_phase - set(ordered))
            ordered.extend(remaining)
        return ordered

    def _rebuild_language_index(self) -> None:
        language_map: dict[str, list[str]] = defaultdict(list)
        for name in self._ordered:
            tool = self._tools[name]
            for language in tool.languages:
                bucket = language_map[language]
                if name not in bucket:
                    bucket.append(name)
        self._by_language = language_map


DEFAULT_REGISTRY = ToolRegistry()


def register_tool(tool: Tool) -> None:
    """Convenience helper mirroring the legacy global registration."""
    DEFAULT_REGISTRY.register(tool)
