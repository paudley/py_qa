# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Tool registry providing discovery by name or language."""

from __future__ import annotations

import heapq
from collections import defaultdict
from collections.abc import Iterable, Iterator, Mapping, Sequence

from .base import PHASE_NAMES, Tool


class ToolRegistry(Mapping[str, Tool]):
    """Central registry for tool definitions.

    ``ToolRegistry`` behaves like a read-only mapping whose keys are tool names
    and whose values are :class:`Tool` instances. It also exposes helpers for
    discovering tools by language and registering new adapters.
    """

    _PHASE_ORDER: tuple[str, ...] = PHASE_NAMES

    def __init__(self) -> None:
        """Initialise an empty tool registry."""

        self._tools: dict[str, Tool] = {}
        self._by_language: dict[str, list[str]] = defaultdict(list)
        self._ordered: tuple[str, ...] = ()

    def register(self, tool: Tool) -> None:
        """Register ``tool`` with the registry enforcing uniqueness by name.

        Args:
            tool: Tool definition to insert into the registry.

        Raises:
            ValueError: If a tool with the same name is already registered.
        """

        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' already registered")
        self._tools[tool.name] = tool
        self._recompute_order()

    def reset(self) -> None:
        """Remove all tools from the registry."""
        self._tools.clear()
        self._by_language.clear()
        self._ordered = ()

    def try_get(self, name: str) -> Tool | None:
        """Return the tool named ``name`` when registered, otherwise ``None``.

        Args:
            name: Tool name to retrieve.

        Returns:
            Tool | None: Registered tool or ``None`` when not found.
        """

        return self._tools.get(name)

    def tools(self) -> Iterable[Tool]:
        """Return an iterable of all registered tools.

        Returns:
            Iterable[Tool]: Iterable yielding tools in execution order.
        """

        return tuple(self._tools[name] for name in self._ordered)

    def tools_for_language(self, language: str) -> Iterable[Tool]:
        """Return tools associated with ``language``.

        Args:
            language: Language identifier used to filter tools.

        Returns:
            Iterable[Tool]: Iterable of tools targeting the supplied language.
        """

        names = self._by_language.get(language, [])
        return tuple(self._tools[name] for name in names if name in self._tools)

    def __len__(self) -> int:
        """Return the number of registered tools.

        Returns:
            int: Count of registered tools.
        """

        return len(self._tools)

    def __iter__(self) -> Iterator[str]:
        """Iterate over tool names in execution order.

        Returns:
            Iterator[str]: Iterator yielding tool names.
        """

        return iter(self._ordered)

    def __getitem__(self, name: str) -> Tool:
        """Return the tool identified by ``name``.

        Args:
            name: Tool name to retrieve.

        Returns:
            Tool: Registered tool associated with ``name``.

        Raises:
            KeyError: If ``name`` does not refer to a registered tool.
        """

        return self._tools[name]

    def _recompute_order(self) -> None:
        """Rebuild the execution order and language index for registered tools."""

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

    def _order_phase(self, tools: Sequence[Tool]) -> list[str]:
        """Return tool names ordered according to ``before``/``after`` constraints.

        Args:
            tools: Tools sharing the same phase.

        Returns:
            list[str]: Tool names ordered within the phase.
        """

        adjacency, indegree = self._build_phase_graph(tools)
        ordered: list[str] = []
        iteration_count = len(indegree)
        ready = [name for name, count in indegree.items() if count == 0]
        heapq.heapify(ready)

        for _ in range(iteration_count):
            if not ready:
                break
            current = heapq.heappop(ready)
            ordered.append(current)
            for neighbour in sorted(adjacency.get(current, ())):
                indegree[neighbour] -= 1
                if indegree[neighbour] == 0:
                    heapq.heappush(ready, neighbour)

        names_in_phase = set(indegree)
        if len(ordered) != len(names_in_phase):
            ordered.extend(sorted(names_in_phase - set(ordered)))
        return ordered

    def _build_phase_graph(
        self,
        tools: Sequence[Tool],
    ) -> tuple[dict[str, set[str]], dict[str, int]]:
        """Return adjacency and indegree structures for ``tools``.

        Args:
            tools: Tools sharing the same phase.

        Returns:
            tuple[dict[str, set[str]], dict[str, int]]: Adjacency list and indegree map.
        """

        names_in_phase = {tool.name for tool in tools}
        adjacency: dict[str, set[str]] = {tool.name: set() for tool in tools}
        indegree: dict[str, int] = {tool.name: 0 for tool in tools}

        for tool in tools:
            for successor in tool.before:
                if successor in names_in_phase:
                    adjacency[tool.name].add(successor)
            for predecessor in tool.after:
                if predecessor in names_in_phase:
                    adjacency.setdefault(predecessor, set()).add(tool.name)

        for targets in adjacency.values():
            for target in targets:
                indegree[target] = indegree.get(target, 0) + 1

        return adjacency, indegree

    def _rebuild_language_index(self) -> None:
        """Rebuild the language-to-tool index based on the current registry order."""

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
    """Register ``tool`` using the shared global registry.

    Args:
        tool: Tool definition to register with :data:`DEFAULT_REGISTRY`.
    """
    DEFAULT_REGISTRY.register(tool)
