# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Rendering helpers for ``lint --explain-tools``."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from rich.console import Console
from rich.table import Table

from pyqa.interfaces.orchestration_selection import SelectionResult, ToolDecision
from pyqa.tools.base import Tool
from pyqa.tools.registry import ToolRegistry

from .runtime import LintRuntimeContext

_CHECKMARK = "✓"
_CROSS = "✗"
_SKIP_ACTION: Final[str] = "skip"


@dataclass(frozen=True, slots=True)
class ExplainToolRow:
    """Row data describing a tool-selection decision."""

    order: int | None
    tool: str
    family: str
    action: str
    reasons: tuple[str, ...]
    indicators: tuple[str, ...]
    description: str


def render_explain_tools(runtime: LintRuntimeContext, selection: SelectionResult) -> list[ExplainToolRow]:
    """Render a summary table describing tool-selection decisions.

    Args:
        runtime: Execution runtime supplying registry and logging services.
        selection: Planned tool selection emitted by the orchestration layer.

    Returns:
        list[ExplainToolRow]: Row data describing the rendered table.
    """

    logger = runtime.state.logger
    table = Table(title="Tool Selection Plan", show_lines=False, box=None)
    table.add_column("Order", justify="right", style="bold")
    table.add_column("Tool", style="bold", no_wrap=True)
    table.add_column("Family", style="dim")
    table.add_column("Action", style="bold")
    table.add_column("Reasons", overflow="fold")
    table.add_column("Indicators", overflow="fold", style="dim")
    table.add_column("Description", overflow="fold", no_wrap=False)

    run_index = {name: index + 1 for index, name in enumerate(selection.run_names)}
    registry = runtime.registry

    sorted_decisions = sorted(selection.decisions, key=lambda decision: decision.name.lower())
    rows: list[ExplainToolRow] = []

    for decision in sorted_decisions:
        reason_text = ", ".join(decision.reasons) if decision.reasons else ""
        indicator_tokens = _indicator_tokens(decision)
        indicator_text = " ".join(indicator_tokens)
        order_value = run_index.get(decision.name)
        order_display = str(order_value) if order_value is not None else "—"
        description = _lookup_description(registry, decision.name)
        table.add_row(
            order_display,
            decision.name,
            decision.family,
            decision.action,
            reason_text,
            indicator_text,
            description,
        )
        rows.append(
            ExplainToolRow(
                order=order_value,
                tool=decision.name,
                family=decision.family,
                action=decision.action,
                reasons=decision.reasons,
                indicators=tuple(indicator_tokens),
                description=description,
            ),
        )

    logger.console.print(table)
    run_count = len(selection.run_names)
    skip_count = sum(1 for decision in selection.decisions if decision.action == _SKIP_ACTION)
    logger.ok(f"Planned {run_count} tool(s); skipped {skip_count} tool(s).")
    considered = ", ".join(sorted(decision.name for decision in selection.decisions))
    if considered:
        logger.ok(f"Tools considered: {considered}")
    return rows


def _indicator_tokens(decision: ToolDecision) -> tuple[str, ...]:
    """Return indicator tokens for ``decision``.

    Args:
        decision: Tool selection decision whose metadata should be summarised.

    Returns:
        tuple[str, ...]: Indicator tokens describing decision metadata.
    """

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
    return tuple(parts)


def _format_toggle(label: str, value: bool) -> str:
    """Return an indicator string describing the boolean toggle state.

    Args:
        label: Indicator label to present.
        value: Toggle state associated with ``label``.

    Returns:
        str: Formatted label paired with a checkmark or cross symbol.
    """

    return f"{label}={_CHECKMARK if value else _CROSS}"


def _lookup_description(registry: ToolRegistry, tool_name: str) -> str:
    """Return the registry description for ``tool_name`` when available.

    Args:
        registry: Tool registry queried for descriptions.
        tool_name: Name of the tool whose description should be retrieved.

    Returns:
        str: Description string or an empty string when undefined.
    """

    tool: Tool | None = registry.try_get(tool_name)
    if tool is None:
        return ""
    return tool.description or ""


def write_explain_tools_json(target: Path, rows: Sequence[ExplainToolRow], console: Console) -> None:
    """Serialise explain-tools rows to ``target`` as JSON.

    Args:
        target: Destination path, or ``-`` to emit directly to stdout.
        rows: Materialised rows returned by ``render_explain_tools``.
        console: Rich console used when printing to stdout.
    """

    payload = [
        {
            "order": row.order,
            "tool": row.tool,
            "family": row.family,
            "action": row.action,
            "reasons": list(row.reasons),
            "indicators": list(row.indicators),
            "description": row.description,
        }
        for row in rows
    ]
    serialized = json.dumps(payload, indent=2)
    if str(target) == "-":
        console.print(serialized)
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(serialized + "\n", encoding="utf-8")


__all__ = ["ExplainToolRow", "render_explain_tools", "write_explain_tools_json"]
