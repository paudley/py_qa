# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Tool selection helpers for orchestrating lint and analysis actions."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from graphlib import CycleError, TopologicalSorter
from pathlib import Path
from typing import Final

from pyqa.platform.languages import detect_languages

from ..config import Config, SensitivityLevel
from ..interfaces.orchestration_selection import (
    PhaseLiteral,
    SelectionContext,
    SelectionResult,
    ToolDecision,
    ToolEligibility,
    ToolFamilyLiteral,
)
from ..orchestration.selection_context import (
    DEFAULT_PHASE,
    PHASE_ORDER,
    UnknownToolRequestedError,
    build_selection_context,
)
from ..tools.base import Tool
from ..tools.registry import ToolRegistry

_DEFAULT_PHASE: Final[PhaseLiteral] = DEFAULT_PHASE


@dataclass(slots=True)
class ToolSelector:
    """Plan tool execution order based on configuration and metadata."""

    registry: ToolRegistry
    last_result: SelectionResult | None = field(default=None, init=False, repr=False)

    def select_tools(self, cfg: Config, files: Sequence[Path], root: Path) -> Sequence[str]:
        """Return tool names for the current run respecting configuration."""

        result = self.plan_selection(cfg, files, root)
        return result.ordered

    def plan_selection(self, cfg: Config, files: Sequence[Path], root: Path) -> SelectionResult:
        """Return a :class:`SelectionResult` that details tool decisions."""

        context = self._build_context(cfg, files, root)
        decisions = self._evaluate_with_only(context) if context.requested_only else self._evaluate_standard(context)
        if context.requested_only:
            unknown_requested = [
                decision.name
                for decision in decisions
                if decision.eligibility.requested_via_only and not decision.eligibility.available
            ]
            if unknown_requested:
                raise UnknownToolRequestedError(self._deduplicate(unknown_requested))
        run_candidates = [
            decision.name for decision in decisions if decision.action == "run" and decision.eligibility.available
        ]
        ordered = tuple(self.order_tools(dict.fromkeys(run_candidates)))
        result = SelectionResult(ordered=ordered, decisions=tuple(decisions), context=context)
        self.last_result = result
        return result

    def order_tools(self, tool_names: Mapping[str, None] | Sequence[str]) -> list[str]:
        """Order tools based on phase metadata and declared dependencies."""

        ordered_input = self._deduplicate(tool_names)
        tools = self._collect_available_tools(ordered_input)
        filtered = [name for name in ordered_input if name in tools]
        if not filtered:
            return []

        phase_groups, unknown_phases = self._group_tools_by_phase(filtered, tools)
        fallback_index = {name: index for index, name in enumerate(filtered)}
        bucketed: list[list[str]] = []

        for phase in PHASE_ORDER:
            names = phase_groups.get(phase)
            if names:
                bucketed.append(self._order_phase(names, tools, fallback_index))

        for other_phase in sorted(unknown_phases):
            names = phase_groups.get(other_phase)
            if names:
                bucketed.append(self._order_phase(names, tools, fallback_index))

        flattened = [name for bucket in bucketed for name in bucket]
        remaining = [name for name in filtered if name not in flattened]
        return flattened + remaining

    # ------------------------------------------------------------------
    # Context & evaluation helpers

    def _build_context(self, cfg: Config, files: Sequence[Path], root: Path) -> SelectionContext:
        return build_selection_context(
            cfg,
            files,
            detected_languages=detect_languages(root, files),
            root=root,
        )

    def _evaluate_with_only(self, context: SelectionContext) -> list[ToolDecision]:
        requested_lookup: dict[str, str] = {}
        for name in context.requested_only:
            lowered = name.lower()
            if lowered not in requested_lookup:
                requested_lookup[lowered] = name

        decisions: list[ToolDecision] = []
        available_lower = {tool.name.lower(): tool for tool in self.registry.tools()}

        for tool in self.registry.tools():
            lowered = tool.name.lower()
            requested = lowered in requested_lookup
            eligibility = self._build_eligibility(tool, context, requested_via_only=requested)
            reasons = ("requested-via-only",) if requested else ("filtered-by-only",)
            decisions.append(
                ToolDecision(
                    name=tool.name,
                    family=eligibility.family,
                    phase=tool.phase,
                    action="run" if requested else "skip",
                    reasons=reasons,
                    eligibility=eligibility,
                )
            )

        for lowered, original in requested_lookup.items():
            if lowered in available_lower:
                continue
            eligibility = ToolEligibility(
                name=original,
                family="unknown",
                phase=_DEFAULT_PHASE,
                available=False,
                requested_via_only=True,
            )
            decisions.append(
                ToolDecision(
                    name=original,
                    family="unknown",
                    phase=_DEFAULT_PHASE,
                    action="skip",
                    reasons=("unknown-tool",),
                    eligibility=eligibility,
                )
            )
        return decisions

    def _evaluate_standard(self, context: SelectionContext) -> list[ToolDecision]:
        decisions: list[ToolDecision] = []
        internal_enabled = self._sensitivity_enables_internal(context.sensitivity)
        pyqa_scope_active = context.pyqa_workspace or context.pyqa_rules
        for tool in self.registry.tools():
            family = self._family_for_tool(tool)
            if family == "external":
                decision = self._external_decision(tool, context, family)
            elif family == "internal":
                decision = self._internal_decision(
                    tool,
                    family,
                    internal_enabled=internal_enabled,
                )
            else:
                decision = self._internal_pyqa_decision(
                    tool,
                    family,
                    internal_enabled=internal_enabled,
                    pyqa_scope_active=pyqa_scope_active,
                    pyqa_rules=context.pyqa_rules,
                )
            decisions.append(decision)
        return decisions

    # ------------------------------------------------------------------
    # Decision builders

    def _external_decision(
        self,
        tool: Tool,
        context: SelectionContext,
        family: ToolFamilyLiteral,
    ) -> ToolDecision:
        language_match, extension_match, config_match = self._external_indicators(tool, context)
        eligible_sources: list[str] = []
        if tool.languages and language_match:
            eligible_sources.append("language-match")
        if tool.file_extensions and extension_match:
            eligible_sources.append("extension-match")
        if tool.config_files and config_match:
            eligible_sources.append("config-present")

        if tool.languages or tool.file_extensions or tool.config_files:
            should_run = bool(eligible_sources)
        else:
            should_run = True
            eligible_sources.append("no-constraints")

        reasons: list[str] = []
        if should_run:
            reasons.append("workspace-match")
            reasons.extend(eligible_sources)
        else:
            if tool.languages and not language_match:
                reasons.append("no-language-match")
            if tool.file_extensions and not extension_match:
                reasons.append("no-extension-match")
            if tool.config_files and not config_match:
                reasons.append("missing-config")
            if not reasons:
                reasons.append("no-signal")

        eligibility = ToolEligibility(
            name=tool.name,
            family=family,
            phase=tool.phase,
            language_match=language_match if tool.languages else None,
            extension_match=extension_match if tool.file_extensions else None,
            config_match=config_match if tool.config_files else None,
        )
        return ToolDecision(
            name=tool.name,
            family=family,
            phase=tool.phase,
            action="run" if should_run else "skip",
            reasons=tuple(reasons),
            eligibility=eligibility,
        )

    def _internal_decision(
        self,
        tool: Tool,
        family: ToolFamilyLiteral,
        *,
        internal_enabled: bool,
    ) -> ToolDecision:
        default_enabled = bool(tool.default_enabled)
        sensitivity_ok = internal_enabled
        should_run = sensitivity_ok or default_enabled
        reasons: list[str] = []
        if should_run:
            if sensitivity_ok:
                reasons.append("sensitivity>=high")
            if default_enabled and not sensitivity_ok:
                reasons.append("default-enabled")
        else:
            reasons.append("sensitivity-too-low")

        eligibility = ToolEligibility(
            name=tool.name,
            family=family,
            phase=tool.phase,
            sensitivity_ok=sensitivity_ok,
            default_enabled=default_enabled,
        )
        return ToolDecision(
            name=tool.name,
            family=family,
            phase=tool.phase,
            action="run" if should_run else "skip",
            reasons=tuple(reasons),
            eligibility=eligibility,
        )

    def _internal_pyqa_decision(
        self,
        tool: Tool,
        family: ToolFamilyLiteral,
        *,
        internal_enabled: bool,
        pyqa_scope_active: bool,
        pyqa_rules: bool,
    ) -> ToolDecision:
        default_enabled = bool(tool.default_enabled)
        sensitivity_ok = internal_enabled or pyqa_rules
        scope_ok = pyqa_scope_active
        should_run = scope_ok
        reasons: list[str] = []
        if should_run:
            reasons.append("pyqa-scope")
            if pyqa_rules and not internal_enabled:
                reasons.append("forced-by-flag")
            elif internal_enabled:
                reasons.append("sensitivity>=high")
            if default_enabled and not (internal_enabled or pyqa_rules):
                reasons.append("default-enabled")
        else:
            if not scope_ok:
                reasons.append("pyqa-scope-disabled")
            else:
                reasons.append("sensitivity-too-low")

        eligibility = ToolEligibility(
            name=tool.name,
            family=family,
            phase=tool.phase,
            sensitivity_ok=sensitivity_ok,
            pyqa_scope=scope_ok,
            default_enabled=default_enabled,
        )
        return ToolDecision(
            name=tool.name,
            family=family,
            phase=tool.phase,
            action="run" if should_run else "skip",
            reasons=tuple(reasons),
            eligibility=eligibility,
        )

    def _build_eligibility(
        self,
        tool: Tool,
        context: SelectionContext,
        *,
        requested_via_only: bool,
    ) -> ToolEligibility:
        family = self._family_for_tool(tool)
        if family == "external":
            language_match, extension_match, config_match = self._external_indicators(tool, context)
            return ToolEligibility(
                name=tool.name,
                family=family,
                phase=tool.phase,
                requested_via_only=requested_via_only,
                language_match=language_match if tool.languages else None,
                extension_match=extension_match if tool.file_extensions else None,
                config_match=config_match if tool.config_files else None,
            )
        if family == "internal":
            return ToolEligibility(
                name=tool.name,
                family=family,
                phase=tool.phase,
                requested_via_only=requested_via_only,
                sensitivity_ok=self._sensitivity_enables_internal(context.sensitivity),
                default_enabled=bool(tool.default_enabled),
            )
        # internal-pyqa
        return ToolEligibility(
            name=tool.name,
            family=family,
            phase=tool.phase,
            requested_via_only=requested_via_only,
            sensitivity_ok=self._sensitivity_enables_internal(context.sensitivity) or context.pyqa_rules,
            pyqa_scope=context.pyqa_workspace or context.pyqa_rules,
            default_enabled=bool(tool.default_enabled),
        )

    # ------------------------------------------------------------------
    # Predicates

    def _external_indicators(
        self,
        tool: Tool,
        context: SelectionContext,
    ) -> tuple[bool, bool, bool]:
        language_scope = context.language_scope
        language_match = bool(set(tool.languages) & language_scope) if tool.languages else False
        extension_match = bool(
            context.file_extensions & frozenset(extension.lower() for extension in tool.file_extensions)
        )
        config_match = (
            any((context.root / cfg_file).exists() for cfg_file in tool.config_files) if tool.config_files else False
        )
        return language_match, extension_match, config_match

    def _sensitivity_enables_internal(self, sensitivity: SensitivityLevel) -> bool:
        return sensitivity in (SensitivityLevel.HIGH, SensitivityLevel.MAXIMUM)

    def _family_for_tool(self, tool: Tool) -> ToolFamilyLiteral:
        internal_names, internal_pyqa_names = _internal_name_sets()
        tags = set(tool.tags)
        if "internal-pyqa" in tags or tool.name in internal_pyqa_names:
            return "internal-pyqa"
        if "internal-linter" in tags or tool.name in internal_names:
            return "internal"
        return "external"

    # ------------------------------------------------------------------
    # Ordering helpers (unchanged from legacy implementation)

    def _deduplicate(self, tool_names: Mapping[str, None] | Sequence[str]) -> list[str]:
        if isinstance(tool_names, Mapping):
            return list(tool_names.keys())
        return list(dict.fromkeys(tool_names))

    def _collect_available_tools(self, ordered_input: Sequence[str]) -> dict[str, Tool]:
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
        phase_groups: dict[str, list[str]] = {}
        unknown_phases: list[str] = []
        for name in filtered:
            tool = tools[name]
            phase = getattr(tool, "phase", _DEFAULT_PHASE)
            phase_groups.setdefault(phase, []).append(name)
            if phase not in PHASE_ORDER and phase not in unknown_phases:
                unknown_phases.append(phase)
        return phase_groups, unknown_phases

    def _order_phase(
        self,
        names: Sequence[str],
        tools: Mapping[str, Tool],
        fallback_index: Mapping[str, int],
    ) -> list[str]:
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

        sorter: TopologicalSorter[str] = TopologicalSorter()
        for name in names:
            sorter.add(name, *sorted(dependencies[name], key=lambda item: fallback_index.get(item, 0)))
        try:
            ordered = list(sorter.static_order())
        except CycleError:
            return list(names)
        return ordered


@lru_cache(maxsize=1)
def _internal_name_sets() -> tuple[frozenset[str], frozenset[str]]:
    from ..linting.registry import iter_internal_linters

    internal: set[str] = set()
    internal_pyqa: set[str] = set()
    for definition in iter_internal_linters():
        if definition.pyqa_scoped:
            internal_pyqa.add(definition.name)
        else:
            internal.add(definition.name)
    return frozenset(internal), frozenset(internal_pyqa)


__all__ = ["ToolSelector"]
