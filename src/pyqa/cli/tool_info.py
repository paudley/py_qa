# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Detailed tooling information command."""

from __future__ import annotations

from pathlib import Path

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.pretty import Pretty
from rich.table import Table

from ..config import Config, ConfigError
from ..config_loader import ConfigLoader
from ..tools.base import Tool, ToolContext
from ..tools.registry import DEFAULT_REGISTRY
from .utils import ToolStatus, check_tool_status


def run_tool_info(
    tool_name: str,
    root: Path,
    *,
    cfg: Config | None = None,
    console: Console | None = None,
) -> int:
    """Present detailed information about *tool_name* and return an exit status."""
    console = console or Console()

    tool = DEFAULT_REGISTRY.try_get(tool_name)
    if tool is None:
        console.print(Panel(f"[red]Unknown tool:[/red] {tool_name}", border_style="red"))
        return 1

    if cfg is None:
        loader = ConfigLoader.for_root(root)
        try:
            load_result = loader.load_with_trace()
        except ConfigError as exc:
            console.print(
                Panel(f"[red]Failed to load configuration:[/red] {exc}", border_style="red"),
            )
            return 1
        current_cfg = load_result.config
    else:
        current_cfg = cfg
        load_result = None

    status = check_tool_status(tool)

    console.print(Panel(f"[bold cyan]{tool.name}[/bold cyan]", title="Tool"))

    overrides = current_cfg.tool_settings.get(tool.name, {}) or {}

    console.print(_build_metadata_table(tool, status))
    console.print(_build_actions_table(tool, current_cfg, root, overrides))

    if overrides:
        console.print(
            Panel(
                Pretty(overrides),
                title="Configuration Overrides",
                border_style="yellow",
            ),
        )
    else:
        console.print(
            Panel(
                "No tool-specific overrides detected.",
                title="Configuration",
                border_style="green",
            ),
        )

    if status.raw_output:
        console.print(
            Panel(
                status.raw_output,
                title="Version Command Output",
                border_style="blue",
            ),
        )

    if load_result is not None:
        warnings = [
            update for update in load_result.updates if update.section == "tool_settings" and update.field == tool.name
        ]
        if warnings:
            warning_table = Table(title="Configuration Provenance", box=box.SIMPLE)
            warning_table.add_column("Source")
            warning_table.add_column("Value", overflow="fold")
            for update in warnings:
                warning_table.add_row(update.source, Pretty(update.value))
            console.print(warning_table)

    return 0


def _build_metadata_table(tool: Tool, status: ToolStatus) -> Table:
    table = Table(title="Metadata", box=box.SIMPLE, expand=True)
    table.add_column("Field", style="bold")
    table.add_column("Value", overflow="fold")

    table.add_row("Description", tool.description or "-")
    table.add_row("Runtime", tool.runtime)
    table.add_row("Default Enabled", "yes" if tool.default_enabled else "no")
    table.add_row("Auto Install", "yes" if tool.auto_install else "no")
    table.add_row("Prefer Local", "yes" if tool.prefer_local else "no")
    table.add_row("Package", tool.package or "-")
    table.add_row("Min Version", tool.min_version or "-")
    table.add_row("Languages", ", ".join(tool.languages) or "-")
    table.add_row("File Extensions", ", ".join(tool.file_extensions) or "-")
    table.add_row("Config Files", ", ".join(tool.config_files) or "-")
    version_cmd = " ".join(map(str, tool.version_command)) if tool.version_command else "-"
    table.add_row("Version Command", version_cmd)
    table.add_row("Current Version", status.version or "-")
    table.add_row("Status", status.status)
    table.add_row("Notes", status.notes or "-")
    if status.path:
        table.add_row("Executable Path", status.path)
    return table


def _build_actions_table(
    tool: Tool,
    cfg: Config,
    root: Path,
    overrides: dict[str, object],
) -> Table:
    table = Table(title="Actions", box=box.SIMPLE, expand=True)
    table.add_column("Name", style="bold")
    table.add_column("Type")
    table.add_column("Command", overflow="fold")
    table.add_column("Description", overflow="fold")

    for action in tool.actions:
        action_type = "fix" if action.is_fix else "check"
        if action.ignore_exit:
            action_type += " (ignore-exit)"
        context = ToolContext(
            cfg=cfg,
            root=root,
            files=tuple(),
            settings=dict(overrides) if overrides else {},
        )
        command = action.build_command(context)
        command_str = " ".join(map(str, command)) if command else "-"
        table.add_row(action.name, action_type, command_str, action.description or "-")
    return table


__all__ = ["run_tool_info"]
