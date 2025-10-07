# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Data structures and errors for the tool-info CLI plumbing."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rich.console import Console

from pyqa.core.config.loader import FieldUpdate

from ....catalog.model_catalog import CatalogSnapshot
from ....catalog.model_tool import ToolDefinition
from ....config import Config
from ....tools.base import Tool
from ...core.shared import CLIError
from ...core.utils import ToolStatus


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
