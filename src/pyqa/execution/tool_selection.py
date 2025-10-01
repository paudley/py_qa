# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Tool selection helpers for orchestrating lint and analysis actions."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from graphlib import CycleError, TopologicalSorter
from pathlib import Path
from typing import Final

from ..config import Config
from ..languages import detect_languages
from ..tools import Tool
from ..tools.registry import ToolRegistry

_DEFAULT_PHASE: Final[str] = "lint"
_PHASE_ORDER: Final[tuple[str, ...]] = (
    "format",
    "lint",
    "analysis",
    "security",
    "test",
    "coverage",
    "utility",
)


@dataclass(slots=True)
class ToolSelector:
    """Plan tool execution order based on configuration and metadata."""

    registry: ToolRegistry

    def select_tools(self, cfg: Config, files: Sequence[Path], root: Path) -> Sequence[str]:
        """Return tool names for the current run respecting configuration.

        Args:
            cfg: Global configuration containing execution preferences.
            files: Files discovered for the lint run.
            root: Workspace root used for language detection.

        Returns:
            Sequence[str]: Ordered list of tool names to execute.
        """

        exec_cfg = cfg.execution
        if exec_cfg.only:
            return self.order_tools(dict.fromkeys(exec_cfg.only))
        languages = list(dict.fromkeys(exec_cfg.languages)) if exec_cfg.languages else []
        if not languages:
            languages = sorted(detect_languages(root, files))
        if languages:
            tool_names: list[str] = []
            for lang in languages:
                tool_names.extend(tool.name for tool in self.registry.tools_for_language(lang))
            if tool_names:
                return self.order_tools(dict.fromkeys(tool_names))
        default_tools = [tool.name for tool in self.registry.tools() if tool.default_enabled]
        return self.order_tools(dict.fromkeys(default_tools))

    def order_tools(self, tool_names: Mapping[str, None] | Sequence[str]) -> list[str]:
        """Order tools based on phase metadata and declared dependencies.

        Args:
            tool_names: Candidate tool names, possibly containing duplicates.

        Returns:
            list[str]: Ordered tool names respecting phase sequencing.
        """

        ordered_input = self._deduplicate(tool_names)
        tools = self._collect_available_tools(ordered_input)
        filtered = [name for name in ordered_input if name in tools]
        if not filtered:
            return []

        phase_groups, unknown_phases = self._group_tools_by_phase(filtered, tools)
        fallback_index = {name: index for index, name in enumerate(filtered)}
        bucketed: list[list[str]] = []

        for phase in _PHASE_ORDER:
            names = phase_groups.get(phase)
            if names:
                bucketed.append(self._order_phase(names, tools, fallback_index))

        for phase in sorted(unknown_phases):
            names = phase_groups.get(phase)
            if names:
                bucketed.append(self._order_phase(names, tools, fallback_index))

        flattened = [name for bucket in bucketed for name in bucket]
        remaining = [name for name in filtered if name not in flattened]
        return flattened + remaining

    def _deduplicate(self, tool_names: Mapping[str, None] | Sequence[str]) -> list[str]:
        """Return tool names with duplicates removed while preserving order.

        Args:
            tool_names: Candidate tool names that may contain duplicates.

        Returns:
            list[str]: Deduplicated tool names in their original order.
        """

        if isinstance(tool_names, Mapping):
            return list(tool_names.keys())
        return list(dict.fromkeys(tool_names))

    def _collect_available_tools(self, ordered_input: Sequence[str]) -> dict[str, Tool]:
        """Return tools that are present in the registry.

        Args:
            ordered_input: Tool names requested by the caller.

        Returns:
            dict[str, Tool]: Mapping of available tool names to their instances.
        """

        available: dict[str, Tool] = {}
        for name in ordered_input:
            tool = self.registry.try_get(name)
            if tool is not None:
                available[name] = tool
        return available

    def _group_tools_by_phase(
        self,
        filtered: Sequence[str],
        tools: Mapping[str, Tool],
    ) -> tuple[dict[str, list[str]], list[str]]:
        """Group ``filtered`` tool names by phase and return unknown phases.

        Args:
            filtered: Tool names confirmed to exist in the registry.
            tools: Mapping of tool names to their metadata.

        Returns:
            tuple[dict[str, list[str]], list[str]]: Phase group mapping and
            list of unknown phases encountered.
        """

        phase_groups: dict[str, list[str]] = {}
        unknown_phases: list[str] = []
        for name in filtered:
            tool = tools[name]
            phase = getattr(tool, "phase", _DEFAULT_PHASE)
            phase_groups.setdefault(phase, []).append(name)
            if phase not in _PHASE_ORDER and phase not in unknown_phases:
                unknown_phases.append(phase)
        return phase_groups, unknown_phases

    def _order_phase(
        self,
        names: Sequence[str],
        tools: Mapping[str, Tool],
        fallback_index: Mapping[str, int],
    ) -> list[str]:
        """Topologically order tools within the same phase.

        Args:
            names: Tool names that share a common execution phase.
            tools: Mapping of tool names to their metadata.
            fallback_index: Stable ordering used when constraints are absent.

        Returns:
            list[str]: Ordered tool names satisfying declared dependencies.
        """

        if len(names) <= 1:
            return list(names)

        dependencies: dict[str, set[str]] = {name: set() for name in names}
        for name in names:
            tool = tools[name]
            for dep in getattr(tool, "after", ()):  # tools that must precede this one
                if dep in dependencies:
                    dependencies[name].add(dep)
            for succ in getattr(tool, "before", ()):  # tools that must follow this one
                if succ in dependencies:
                    dependencies[succ].add(name)

        sorter = TopologicalSorter()
        for name in names:
            sorter.add(name, *sorted(dependencies[name], key=lambda item: fallback_index.get(item, 0)))
        try:
            ordered = list(sorter.static_order())
        except CycleError:
            return list(names)
        return ordered


__all__ = ["ToolSelector"]
