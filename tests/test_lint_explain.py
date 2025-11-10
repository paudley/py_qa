# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Tests for the explain-tools rendering helpers."""

from __future__ import annotations

from io import StringIO
from types import SimpleNamespace

from rich.console import Console

from pyqa.cli.commands.lint.explain import render_explain_tools
from pyqa.orchestration.tool_selection import SelectionResult, ToolDecision, ToolEligibility


def test_render_explain_tools_shows_order_and_description() -> None:
    console_stream = StringIO()
    console = Console(file=console_stream, force_terminal=False, color_system=None)

    class _ExplainLogger:
        def __init__(self) -> None:
            self.console = console
            self.ok_messages: list[str] = []

        def ok(self, message: str) -> None:
            self.ok_messages.append(message)

        def warn(self, message: str) -> None:  # pragma: no cover - unused stub
            self.ok_messages.append(message)

        def fail(self, message: str) -> None:  # pragma: no cover - unused stub
            self.ok_messages.append(message)

    class _Registry:
        def __init__(self) -> None:
            self._tools = {
                "alpha": SimpleNamespace(description="Alpha internal linter"),
                "beta": SimpleNamespace(description="Beta formatter"),
                "gamma": SimpleNamespace(description="Gamma analyzer"),
            }

        def try_get(self, name: str):
            return self._tools.get(name)

    eligibility_run = ToolEligibility(
        name="alpha",
        family="internal",
        phase="lint",
        available=True,
        requested_via_only=False,
        language_match=True,
        extension_match=True,
        config_match=None,
        sensitivity_ok=True,
        pyqa_scope=None,
        default_enabled=True,
    )
    eligibility_skip = ToolEligibility(
        name="beta",
        family="external",
        phase="lint",
        available=True,
        requested_via_only=False,
        language_match=False,
        extension_match=False,
        config_match=False,
        sensitivity_ok=None,
        pyqa_scope=None,
        default_enabled=False,
    )

    selection = SelectionResult(
        ordered=("gamma",),
        decisions=(
            ToolDecision(
                name="beta",
                family="external",
                phase="lint",
                action="skip",
                reasons=("no-language-match",),
                eligibility=eligibility_skip,
            ),
            ToolDecision(
                name="alpha",
                family="internal",
                phase="lint",
                action="run",
                reasons=("workspace-match",),
                eligibility=eligibility_run,
            ),
            ToolDecision(
                name="gamma",
                family="internal",
                phase="lint",
                action="run",
                reasons=("workspace-match",),
                eligibility=ToolEligibility(
                    name="gamma",
                    family="internal",
                    phase="lint",
                    available=True,
                    requested_via_only=False,
                    language_match=True,
                    extension_match=True,
                    config_match=None,
                    sensitivity_ok=True,
                    pyqa_scope=None,
                    default_enabled=True,
                ),
            ),
        ),
        context=SimpleNamespace(),
    )

    runtime = SimpleNamespace(state=SimpleNamespace(logger=_ExplainLogger()), registry=_Registry())
    rows = render_explain_tools(runtime, selection)

    output = console_stream.getvalue()
    assert "Order" in output
    assert "Description" in output
    assert any(row.description == "Alpha internal linter" for row in rows)
    row_map = {row.tool: row for row in rows}
    assert row_map["gamma"].order == 1
