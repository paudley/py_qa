# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Render refactor navigator panels for concise output."""

from __future__ import annotations

from rich import box
from rich.panel import Panel
from rich.table import Table

from pyqa.runtime.console import console_manager

from ...config import OutputConfig
from ...core.models import RunResult


def render_refactor_navigator(result: RunResult, cfg: OutputConfig) -> None:
    """Render the refactor navigator panel when analysis data is available.

    Args:
        result: Completed run result containing analysis metadata.
        cfg: Output configuration describing formatting preferences.
    """

    navigator = result.analysis.get("refactor_navigator")
    if not navigator:
        return

    console = console_manager.get(color=cfg.color, emoji=cfg.emoji)
    table = Table(box=box.SIMPLE_HEAVY if cfg.color else box.SIMPLE)
    table.add_column("Function", overflow="fold")
    table.add_column("Issues", justify="right")
    table.add_column("Tags", overflow="fold")
    table.add_column("Size", justify="right")
    table.add_column("Complexity", justify="right")

    for entry in navigator[:5]:
        function = entry.get("function") or "<module>"
        file_path = entry.get("file") or ""
        location = f"{file_path}:{function}" if file_path else function
        issues = sum(int(value) for value in entry.get("issue_tags", {}).values())
        tags = ", ".join(sorted(entry.get("issue_tags", {}).keys()))
        size = entry.get("size")
        complexity = entry.get("complexity")
        table.add_row(
            location,
            str(issues),
            tags or "-",
            "-" if size is None else str(size),
            "-" if complexity is None else str(complexity),
        )

    panel = Panel(
        table,
        title="Refactor Navigator",
        border_style="magenta" if cfg.color else "none",
    )
    console.print(panel)


__all__ = ["render_refactor_navigator"]
