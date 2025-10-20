# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Tool selection helpers for orchestrating lint and analysis actions."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from graphlib import CycleError, TopologicalSorter
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING, Final, Literal, cast

from pyqa.cache.in_memory import memoize
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

if TYPE_CHECKING:
    from ..linting.registry import InternalLinterDefinition

_InternalLinterResolver = Callable[[], Sequence["InternalLinterDefinition"]]


def _resolve_internal_linter_resolver() -> _InternalLinterResolver | None:
    """Return the iterator that yields internal lint definitions when available.

    Returns:
        _InternalLinterResolver | None: Callable that iterates internal linters
            or ``None`` when the linting registry cannot be imported.
    """

    try:
        module = import_module("pyqa.linting.registry")
    except ImportError:  # pragma: no cover - feature optional during bootstrap
        return None
    resolver = getattr(module, "iter_internal_linters", None)
    if resolver is None:
        return None
    return cast(_InternalLinterResolver, resolver)


_ITER_INTERNAL_LINTERS: Final[_InternalLinterResolver | None] = _resolve_internal_linter_resolver()

_DEFAULT_PHASE: Final[PhaseLiteral] = DEFAULT_PHASE
_FAMILY_EXTERNAL: Final[ToolFamilyLiteral] = "external"
_FAMILY_INTERNAL: Final[ToolFamilyLiteral] = "internal"
_FAMILY_INTERNAL_PYQA: Final[ToolFamilyLiteral] = "internal-pyqa"
_FAMILY_UNKNOWN: Final[ToolFamilyLiteral] = "unknown"
_ACTION_RUN: Final[Literal["run"]] = "run"
_ACTION_SKIP: Final[Literal["skip"]] = "skip"
_TAG_INTERNAL_PYQA: Final[str] = "internal-pyqa"
_TAG_INTERNAL: Final[str] = "internal-linter"


@dataclass(slots=True)
class ToolSelector:
    """Plan tool execution order based on configuration and metadata."""

    registry: ToolRegistry
    last_result: SelectionResult | None = field(default=None, init=False, repr=False)

    def select_tools(self, cfg: Config, files: Sequence[Path], root: Path) -> Sequence[str]:
        """Return tool names for the current run respecting configuration.

        Args:
            cfg: Effective configuration for the current invocation.
            files: Files selected for analysis.
            root: Repository root path used for discovery heuristics.

        Returns:
            Sequence[str]: Ordered tool names scheduled to run.
        """

        result = self.plan_selection(cfg, files, root)
        return result.ordered

    def plan_selection(self, cfg: Config, files: Sequence[Path], root: Path) -> SelectionResult:
        """Return a :class:`SelectionResult` that details tool decisions.

        Args:
            cfg: Effective configuration for the current invocation.
            files: Files selected for analysis.
            root: Repository root path used for discovery heuristics.

        Returns:
            SelectionResult: Detailed selection plan including decisions and ordering.
        """

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
            decision.name for decision in decisions if decision.action == _ACTION_RUN and decision.eligibility.available
        ]
        ordered = tuple(self.order_tools(dict.fromkeys(run_candidates)))
        result = SelectionResult(ordered=ordered, decisions=tuple(decisions), context=context)
        self.last_result = result
        return result

    def order_tools(self, tool_names: Mapping[str, None] | Sequence[str]) -> list[str]:
        """Order tools based on phase metadata and declared dependencies.

        Args:
            tool_names: Tool names proposed for execution.

        Returns:
            list[str]: Ordered tool names respecting dependencies and phases.
        """

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
        """Return a :class:`SelectionContext` derived from the current invocation.

        Args:
            cfg: Effective configuration for the current invocation.
            files: Files selected for analysis.
            root: Repository root path used for discovery heuristics.

        Returns:
            SelectionContext: Populated context describing selection parameters.
        """

        detected = tuple(sorted(detect_languages(root, files)))
        return build_selection_context(
            cfg,
            files,
            detected_languages=detected,
            root=root,
        )

    def _evaluate_with_only(self, context: SelectionContext) -> list[ToolDecision]:
        """Return tool decisions when ``--only`` filters are active.

        Args:
            context: Selection context summarising CLI inputs and discovery.

        Returns:
            list[ToolDecision]: Decisions covering requested and skipped tools.
        """

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
                    action=_ACTION_RUN if requested else _ACTION_SKIP,
                    reasons=reasons,
                    eligibility=eligibility,
                )
            )

        for lowered, original in requested_lookup.items():
            if lowered in available_lower:
                continue
            eligibility = ToolEligibility(
                name=original,
                family=_FAMILY_UNKNOWN,
                phase=_DEFAULT_PHASE,
                available=False,
                requested_via_only=True,
            )
            decisions.append(
                ToolDecision(
                    name=original,
                    family=_FAMILY_UNKNOWN,
                    phase=_DEFAULT_PHASE,
                    action=_ACTION_SKIP,
                    reasons=("unknown-tool",),
                    eligibility=eligibility,
                )
            )
        return decisions

    def _evaluate_standard(self, context: SelectionContext) -> list[ToolDecision]:
        """Return tool decisions when running without ``--only`` filtering.

        Args:
            context: Selection context summarising CLI inputs and discovery.

        Returns:
            list[ToolDecision]: Decisions for all registry tools.
        """

        decisions: list[ToolDecision] = []
        internal_enabled = self._sensitivity_enables_internal(context.sensitivity)
        pyqa_scope_active = context.pyqa_workspace or context.pyqa_rules
        for tool in self.registry.tools():
            family = self._family_for_tool(tool)
            if family == _FAMILY_EXTERNAL:
                decision = self._external_decision(tool, context, family)
            elif family == _FAMILY_INTERNAL:
                decision = self._internal_decision(
                    tool,
                    family,
                    internal_enabled=internal_enabled,
                )
            else:
                decision_request = _InternalDecisionRequest(
                    tool=tool,
                    family=family,
                    internal_enabled=internal_enabled,
                    pyqa_scope_active=pyqa_scope_active,
                    pyqa_rules=context.pyqa_rules,
                )
                decision = self._internal_pyqa_decision(decision_request)
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
        """Return the decision for an external tool based on workspace signals.

        Args:
            tool: Tool under evaluation.
            context: Selection context summarising discovery inputs.
            family: Family identifier assigned to the tool.

        Returns:
            ToolDecision: Decision describing whether the tool should run.
        """

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
            action=_ACTION_RUN if should_run else _ACTION_SKIP,
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
        """Return the decision for internal tools governed by sensitivity levels.

        Args:
            tool: Tool under evaluation.
            family: Family identifier assigned to the tool.
            internal_enabled: Flag indicating whether sensitivity permits internal tools.

        Returns:
            ToolDecision: Decision describing whether the tool should run.
        """

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
            action=_ACTION_RUN if should_run else _ACTION_SKIP,
            reasons=tuple(reasons),
            eligibility=eligibility,
        )

    def _internal_pyqa_decision(self, request: _InternalDecisionRequest) -> ToolDecision:
        """Return the decision for internal pyqa tools based on workspace scope.

        Args:
            request: Decision request encapsulating tool metadata and context flags.

        Returns:
            ToolDecision: Decision describing whether the tool should run.
        """

        default_enabled = bool(request.tool.default_enabled)
        sensitivity_ok = request.internal_enabled or request.pyqa_rules
        scope_ok = request.pyqa_scope_active
        should_run = scope_ok
        reasons: list[str] = []
        if should_run:
            reasons.append("pyqa-scope")
            if request.pyqa_rules and not request.internal_enabled:
                reasons.append("forced-by-flag")
            elif request.internal_enabled:
                reasons.append("sensitivity>=high")
            if default_enabled and not (request.internal_enabled or request.pyqa_rules):
                reasons.append("default-enabled")
        else:
            reasons.append("pyqa-scope-disabled")

        eligibility = ToolEligibility(
            name=request.tool.name,
            family=request.family,
            phase=request.tool.phase,
            sensitivity_ok=sensitivity_ok,
            pyqa_scope=scope_ok,
            default_enabled=default_enabled,
        )
        return ToolDecision(
            name=request.tool.name,
            family=request.family,
            phase=request.tool.phase,
            action=_ACTION_RUN if should_run else _ACTION_SKIP,
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
        """Return eligibility metadata for ``tool`` within ``context``.

        Args:
            tool: Tool under evaluation.
            context: Selection context summarising discovery inputs.
            requested_via_only: ``True`` when the tool was explicitly requested via ``--only``.

        Returns:
            ToolEligibility: Eligibility metadata consumed by decision builders.
        """

        family = self._family_for_tool(tool)
        if family == _FAMILY_EXTERNAL:
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
        if family == _FAMILY_INTERNAL:
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
        """Return language, extension, and config matches for an external tool.

        Args:
            tool: Tool under evaluation.
            context: Selection context summarising discovery inputs.

        Returns:
            tuple[bool, bool, bool]: Flags indicating language, extension, and config matches.
        """

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
        """Return ``True`` when ``sensitivity`` enables internal tool execution.

        Args:
            sensitivity: Sensitivity level configured for the run.

        Returns:
            bool: ``True`` when internal tooling should run.
        """

        return sensitivity in (SensitivityLevel.HIGH, SensitivityLevel.MAXIMUM)

    def _family_for_tool(self, tool: Tool) -> ToolFamilyLiteral:
        """Return the tool family identifier for ``tool``.

        Args:
            tool: Tool definition retrieved from the registry.

        Returns:
            ToolFamilyLiteral: Tool family identifier used during selection.
        """

        internal_names, internal_pyqa_names = _internal_name_sets()
        tags = set(tool.tags)
        if _TAG_INTERNAL_PYQA in tags or tool.name in internal_pyqa_names:
            return _FAMILY_INTERNAL_PYQA
        if _TAG_INTERNAL in tags or tool.name in internal_names:
            return _FAMILY_INTERNAL
        return _FAMILY_EXTERNAL

    # ------------------------------------------------------------------
    # Ordering helpers (unchanged from legacy implementation)

    def _deduplicate(self, tool_names: Mapping[str, None] | Sequence[str]) -> list[str]:
        """Return ``tool_names`` without duplicates preserving order.

        Args:
            tool_names: Candidate tool names derived from selection heuristics.

        Returns:
            list[str]: Ordered tool names without duplicates.
        """

        if isinstance(tool_names, Mapping):
            return list(tool_names.keys())
        return list(dict.fromkeys(tool_names))

    def _collect_available_tools(self, ordered_input: Sequence[str]) -> dict[str, Tool]:
        """Return tools from the registry matching ``ordered_input`` names.

        Args:
            ordered_input: Tool names provided by selection heuristics.

        Returns:
            dict[str, Tool]: Mapping of tool name to tool definition.
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
        """Return tools grouped by phase and a list of unknown phases.

        Args:
            filtered: Ordered tool names that passed preliminary filtering.
            tools: Mapping of tool names to tool definitions.

        Returns:
            tuple[dict[str, list[str]], list[str]]: Phase grouping and unknown phase names.
        """

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
        """Return tools ordered within a phase respecting dependencies.

        Args:
            names: Tool names that share the same phase.
            tools: Mapping of tool names to tool definitions.
            fallback_index: Original ordering used to break dependency ties.

        Returns:
            list[str]: Tool names ordered within the phase.
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

        sorter: TopologicalSorter[str] = TopologicalSorter()
        for name in names:
            sorter.add(name, *sorted(dependencies[name], key=lambda item: fallback_index.get(item, 0)))
        try:
            ordered = list(sorter.static_order())
        except CycleError:
            return list(names)
        return ordered


@memoize(maxsize=1)
def _internal_name_sets() -> tuple[frozenset[str], frozenset[str]]:
    """Return cached internal and internal-pyqa tool name sets.

    Returns:
        tuple[frozenset[str], frozenset[str]]: Tuple of (internal, internal_pyqa) tool names.
    """

    if _ITER_INTERNAL_LINTERS is None:
        return frozenset(), frozenset()

    internal: set[str] = set()
    internal_pyqa: set[str] = set()
    for definition in _ITER_INTERNAL_LINTERS():
        destination = internal_pyqa if definition.pyqa_scoped else internal
        destination.add(definition.name)
    return frozenset(internal), frozenset(internal_pyqa)


__all__ = ["ToolSelector", "SelectionResult", "ToolDecision"]


@dataclass(slots=True)
class _InternalDecisionRequest:
    """Inputs controlling internal pyqa decision evaluation."""

    tool: Tool
    family: ToolFamilyLiteral
    internal_enabled: bool
    pyqa_scope_active: bool
    pyqa_rules: bool
