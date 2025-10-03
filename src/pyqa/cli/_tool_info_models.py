# SPDX-License-Identifier: MIT
"""Data structures and errors for the tool-info CLI plumbing."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rich.console import Console

from ..config import Config
from ..config_loader import FieldUpdate
from ..tooling import CatalogSnapshot, ToolDefinition
from ..tools.base import Tool
from .shared import CLIError
from .utils import ToolStatus


@dataclass(slots=True)
class ToolInfoInputs:
    """Capture CLI parameters prior to orchestration."""

    tool_name: str
    root: Path
    console: Console
    cfg: Config | None
    catalog_snapshot: CatalogSnapshot | None


@dataclass(slots=True)
class ToolInfoConfigData:
    """Configuration payload used during tool information rendering."""

    config: Config
    warnings: tuple[str, ...]
    updates: tuple[FieldUpdate, ...]


@dataclass(slots=True)
class ToolInfoContext:
    """Fully resolved tool-info context ready for rendering."""

    inputs: ToolInfoInputs
    config: ToolInfoConfigData
    tool: Tool
    status: ToolStatus
    overrides: dict[str, object]
    catalog_snapshot: CatalogSnapshot
    catalog_tool: ToolDefinition | None


ToolInfoError = CLIError


__all__ = [
    "ToolInfoContext",
    "ToolInfoConfigData",
    "ToolInfoInputs",
    "ToolInfoError",
]
