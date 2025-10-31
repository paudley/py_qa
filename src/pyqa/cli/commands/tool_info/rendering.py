# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Rendering helpers for the tool-info command."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import cast

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.pretty import Pretty
from rich.table import Table

from pyqa.core.config.loader import FieldUpdate
from pyqa.interfaces.config import Config as ConfigProtocol
from pyqa.interfaces.tools import ToolContext as ToolContextView

from ....catalog.model_tool import ToolDefinition
from ....config.types import ConfigValue
from ....tools.base import Tool
from ....tools.base import ToolContext as ToolContextModel
from ...core.utils import ToolStatus


def build_metadata_table(
    tool: Tool,
    status: ToolStatus,
    catalog_tool: ToolDefinition | None = None,
) -> Table:
    """Return a rich table describing static and runtime tool metadata.

    Args:
        tool: Tool definition retrieved from the registry.
        status: Runtime status information gathered from the environment.
        catalog_tool: Optional catalog definition providing additional details.

    Returns:
        Table: Rich table instance ready for rendering.
    """

    table = Table(title="Metadata", box=box.SIMPLE, expand=True)
    table.add_column("Field", style="bold")
    table.add_column("Value", overflow="fold")

    table.add_row("Description", tool.description or "-")
    table.add_row("Runtime", tool.runtime)
    table.add_row("Default Enabled", _yes_no(tool.default_enabled))
    table.add_row("Auto Install", _yes_no(tool.auto_install))
    table.add_row("Prefer Local", _yes_no(tool.prefer_local))
    table.add_row("Package", tool.package or "-")
    table.add_row("Min Version", tool.min_version or "-")
    table.add_row("Languages", ", ".join(tool.languages) or "-")
    table.add_row("File Extensions", ", ".join(tool.file_extensions) or "-")
    table.add_row("Config Files", ", ".join(tool.config_files) or "-")
    if catalog_tool is not None:
        table.add_row("Phase", catalog_tool.phase)
    version_cmd = " ".join(str(part) for part in tool.version_command) if tool.version_command else "-"
    table.add_row("Version Command", version_cmd)
    table.add_row("Current Version", status.version.detected or "-")
    table.add_row("Status", status.availability.value)
    table.add_row("Notes", status.notes or "-")
    if status.execution.path:
        table.add_row("Executable Path", status.execution.path)
    return table


def build_actions_table(
    tool: Tool,
    cfg: ConfigProtocol,
    root: Path,
    overrides: dict[str, ConfigValue],
) -> Table:
    """Return a rich table describing the tool's registered actions.

    Args:
        tool: Tool definition containing registered actions.
        cfg: Active configuration object for contextual command building.
        root: Project root directory supplying relative path context.
        overrides: Tool-specific configuration overrides.

    Returns:
        Table: Rich table instance enumerating tool actions.
    """

    table = Table(title="Actions", box=box.SIMPLE, expand=True)
    table.add_column("Name", style="bold")
    table.add_column("Type")
    table.add_column("Command", overflow="fold")
    table.add_column("Description", overflow="fold")

    for action in tool.actions:
        action_type = "fix" if action.is_fix else "check"
        if action.ignore_exit:
            action_type += " (ignore-exit)"
        context = ToolContextModel(
            cfg=cfg,
            root=root,
            files=tuple(),
            settings=dict(overrides) if overrides else {},
        )
        command = action.build_command(cast(ToolContextView, context))
        command_str = " ".join(str(part) for part in command) if command else "-"
        table.add_row(action.name, action_type, command_str, action.description or "-")
    return table


def render_documentation(console: Console, tool: Tool) -> None:
    """Render optional documentation sections for ``tool``.

    Args:
        console: Rich console used for output.
        tool: Tool definition that may expose documentation content.
    """

    documentation = getattr(tool, "documentation", None)
    if documentation is None:
        return

    if documentation.help is not None:
        console.print(Panel(documentation.help.content, title="Help", border_style="cyan"))

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


def render_overrides_panel(console: Console, overrides: dict[str, ConfigValue]) -> None:
    """Render configuration override information.

    Args:
        console: Rich console used for output.
        overrides: Tool-specific configuration overrides.
    """

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


def render_raw_output(console: Console, status: ToolStatus) -> None:
    """Render raw version command output when available.

    Args:
        console: Rich console used for output.
        status: Runtime status describing command execution results.
    """

    if not status.raw_output:
        return
    console.print(
        Panel(
            status.raw_output,
            title="Version Command Output",
            border_style="blue",
        ),
    )


def render_provenance(
    console: Console,
    updates: Sequence[FieldUpdate],
) -> None:
    """Render configuration provenance updates affecting the tool.

    Args:
        console: Rich console used for output.
        updates: Sequence of configuration updates relevant to the tool.
    """

    if not updates:
        return
    table = Table(title="Configuration Provenance", box=box.SIMPLE)
    table.add_column("Source")
    table.add_column("Value", overflow="fold")
    for update in updates:
        table.add_row(update.source, Pretty(update.value))
    console.print(table)


def render_warnings(console: Console, warnings: Sequence[str]) -> None:
    """Render configuration warnings encountered during loading.

    Args:
        console: Rich console used for output.
        warnings: Iterable of warning messages to render.
    """

    for message in warnings:
        console.print(Panel(f"[yellow]Warning:[/yellow] {message}", border_style="yellow"))


def _yes_no(value: bool) -> str:
    """Return ``"yes"`` or ``"no"`` for ``value``.

    Args:
        value: Input boolean value.

    Returns:
        str: ``"yes"`` when ``value`` is truthy, otherwise ``"no"``.
    """

    return "yes" if value else "no"


__all__ = [
    "build_actions_table",
    "build_metadata_table",
    "render_documentation",
    "render_overrides_panel",
    "render_provenance",
    "render_raw_output",
    "render_warnings",
]
