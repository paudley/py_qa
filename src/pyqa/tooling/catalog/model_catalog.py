# SPDX-License-Identifier: MIT
"""Catalog aggregate models used by the tooling loader."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from .model_strategy import StrategyDefinition
from .model_tool import ToolDefinition
from .types import JSONValue


@dataclass(frozen=True, slots=True)
class CatalogFragment:
    """Shared catalog fragment intended for reuse across tool definitions."""

    name: str
    data: Mapping[str, JSONValue]
    source: Path


@dataclass(frozen=True, slots=True)
class CatalogSnapshot:
    """Materialised catalog data paired with a deterministic checksum."""

    tools: tuple[ToolDefinition, ...]
    strategies: tuple[StrategyDefinition, ...]
    fragments: tuple[CatalogFragment, ...]
    checksum: str


__all__ = [
    "CatalogFragment",
    "CatalogSnapshot",
]
