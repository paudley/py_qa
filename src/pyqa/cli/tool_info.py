# SPDX-License-Identifier: MIT
"""Detailed tooling information command."""

from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.panel import Panel

from ..config import Config
from ..tooling import CatalogSnapshot
from ._tool_info_models import ToolInfoError, ToolInfoInputs
from ._tool_info_rendering import (
    build_actions_table,
    build_metadata_table,
    render_documentation,
    render_overrides_panel,
    render_provenance,
    render_raw_output,
)
from ._tool_info_services import prepare_context, provenance_updates_for_tool


def run_tool_info(
    tool_name: str,
    root: Path,
    *,
    cfg: Config | None = None,
    console: Console | None = None,
    catalog_snapshot: CatalogSnapshot | None = None,
) -> int:
    """Present detailed information about ``tool_name`` and return an exit status.

    Args:
        tool_name: Registry name for the tool to inspect.
        root: Project root directory supplying configuration context.
        cfg: Optional preloaded configuration object.
        console: Optional ``rich`` console for output rendering.
        catalog_snapshot: Optional snapshot providing catalog metadata.

    Returns:
        int: ``0`` when rendering succeeds, ``1`` when a recoverable error occurs.
    """

    inputs = ToolInfoInputs(
        tool_name=tool_name,
        root=root.resolve(),
        console=console or Console(),
        cfg=cfg,
        catalog_snapshot=catalog_snapshot,
    )

    try:
        context = prepare_context(inputs)
    except ToolInfoError as exc:
        inputs.console.print(Panel(f"[red]{exc}[/red]", border_style="red"))
        return exc.exit_code

    console = context.inputs.console
    console.print(Panel(f"[bold cyan]{context.tool.name}[/bold cyan]", title="Tool"))
    console.print(build_metadata_table(context.tool, context.status, context.catalog_tool))
    console.print(
        build_actions_table(
            context.tool,
            context.config.config,
            context.inputs.root,
            context.overrides,
        ),
    )
    render_documentation(console, context.tool)
    render_overrides_panel(console, context.overrides)
    render_raw_output(console, context.status)

    provenance = provenance_updates_for_tool(
        updates=context.config.updates,
        tool_name=context.tool.name,
    )
    render_provenance(console, provenance)

    return 0


__all__ = ["run_tool_info"]
