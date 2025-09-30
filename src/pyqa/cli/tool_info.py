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
from ..tooling import CatalogSnapshot, ToolDefinition
from ..tools.base import Tool, ToolContext
from ..tools.builtins import initialize_registry
from ..tools.registry import DEFAULT_REGISTRY
from .utils import ToolStatus, check_tool_status


def run_tool_info(
    tool_name: str,
    root: Path,
    *,
    cfg: Config | None = None,
    console: Console | None = None,
    catalog_snapshot: CatalogSnapshot | None = None,
) -> int:
    """Present detailed information about *tool_name* and return an exit status."""
    console = console or Console()

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

    if catalog_snapshot is None:
        catalog_snapshot = initialize_registry(registry=DEFAULT_REGISTRY)

    tool = DEFAULT_REGISTRY.try_get(tool_name)
    if tool is None:
        console.print(Panel(f"[red]Unknown tool:[/red] {tool_name}", border_style="red"))
        return 1

    status = check_tool_status(tool)

    console.print(Panel(f"[bold cyan]{tool.name}[/bold cyan]", title="Tool"))

    overrides = current_cfg.tool_settings.get(tool.name, {}) or {}

    catalog_tool = _find_catalog_tool(tool.name, catalog_snapshot)
    console.print(_build_metadata_table(tool, status, catalog_tool))
    console.print(_build_actions_table(tool, current_cfg, root, overrides))
    _render_documentation(console, tool)

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


def _build_metadata_table(
    tool: Tool,
    status: ToolStatus,
    catalog_tool: ToolDefinition | None = None,
) -> Table:
    """Build a rich table containing static and runtime tool metadata.

    Args:
        tool: Tool definition retrieved from the registry.
        status: Runtime status information obtained via :func:`check_tool_status`.
        catalog_tool: Optional catalog definition containing additional metadata.

    Returns:
        Table: Rich table populated with metadata rows for display.

    """

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
    if catalog_tool is not None:
        table.add_row("Phase", catalog_tool.phase)
    version_cmd = " ".join(map(str, tool.version_command)) if tool.version_command else "-"
    table.add_row("Version Command", version_cmd)
    table.add_row("Current Version", status.version.detected or "-")
    table.add_row("Status", status.availability.value)
    table.add_row("Notes", status.notes or "-")
    if status.execution.path:
        table.add_row("Executable Path", status.execution.path)
    return table


def _find_catalog_tool(
    name: str,
    snapshot: CatalogSnapshot | None,
) -> ToolDefinition | None:
    if snapshot is None:
        return None
    for definition in snapshot.tools:
        if definition.name == name or name in definition.aliases:
            return definition
    return None


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


def _render_documentation(console: Console, tool: Tool) -> None:
    documentation = getattr(tool, "documentation", None)
    if documentation is None:
        return

    if documentation.help is not None:
        console.print(
            Panel(
                documentation.help.content,
                title="Help",
                border_style="cyan",
            ),
        )

    if documentation.command is not None:
        console.print(
            Panel(
                documentation.command.content,
                title="Command Reference",
                border_style="cyan",
            ),
        )

    if documentation.shared is not None:
        console.print(
            Panel(
                documentation.shared.content,
                title="Shared Knobs",
                border_style="cyan",
            ),
        )


__all__ = ["run_tool_info"]
