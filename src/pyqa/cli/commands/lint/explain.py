# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Rendering helpers for ``lint --explain-tools``."""

from __future__ import annotations

from rich.table import Table

from ....orchestration.tool_selection import SelectionResult, ToolDecision
from .runtime import LintRuntimeContext

_CHECKMARK = "✓"
_CROSS = "✗"


def render_explain_tools(runtime: LintRuntimeContext, selection: SelectionResult) -> None:
    """Render a summary table describing tool-selection decisions."""

    logger = runtime.state.logger
    table = Table(title="Tool Selection Plan", show_lines=False, box=None)
    table.add_column("Tool", style="bold")
    table.add_column("Family", style="dim")
    table.add_column("Action", style="bold")
    table.add_column("Reasons", overflow="fold")
    table.add_column("Indicators", overflow="fold", style="dim")

    for decision in selection.decisions:
        reasons = ", ".join(decision.reasons) if decision.reasons else ""
        indicators = _format_indicators(decision)
        table.add_row(
            decision.name,
            decision.family,
            decision.action,
            reasons,
            indicators,
        )

    logger.console.print(table)
    run_count = len(selection.run_names)
    skip_count = sum(1 for decision in selection.decisions if decision.action == "skip")
    logger.ok(f"Planned {run_count} tool(s); skipped {skip_count} tool(s).")


def _format_indicators(decision: ToolDecision) -> str:
    """Return a compact indicator string for ``decision``."""

    eligibility = decision.eligibility
    parts: list[str] = []
    if eligibility.requested_via_only:
        parts.append("only")
    if eligibility.language_match is not None:
        parts.append(_format_toggle("lang", eligibility.language_match))
    if eligibility.extension_match is not None:
        parts.append(_format_toggle("ext", eligibility.extension_match))
    if eligibility.config_match is not None:
        parts.append(_format_toggle("config", eligibility.config_match))
    if eligibility.sensitivity_ok is not None:
        parts.append(_format_toggle("sensitivity", eligibility.sensitivity_ok))
    if eligibility.pyqa_scope is not None:
        parts.append(_format_toggle("pyqa", eligibility.pyqa_scope))
    if eligibility.default_enabled:
        parts.append("default")
    if not eligibility.available:
        parts.append("missing")
    return " ".join(parts)


def _format_toggle(label: str, value: bool) -> str:
    return f"{label}={_CHECKMARK if value else _CROSS}"


__all__ = ["render_explain_tools"]
