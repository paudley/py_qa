# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Compatibility shim exposing catalog loader primitives."""

from __future__ import annotations

from .catalog.errors import CatalogIntegrityError, CatalogValidationError
from .catalog.loader import ToolCatalogLoader
from .catalog.models import (
    ActionDefinition,
    CatalogFragment,
    CatalogSnapshot,
    CommandDefinition,
    DiagnosticsBundle,
    DiagnosticsDefinition,
    DocumentationBundle,
    DocumentationEntry,
    OptionDefinition,
    OptionDocumentationBundle,
    OptionGroupDefinition,
    ParserDefinition,
    RuntimeDefinition,
    RuntimeInstallDefinition,
    StrategyConfigField,
    StrategyDefinition,
    StrategyReference,
    StrategyType,
    SuppressionsDefinition,
    ToolDefinition,
)
from .catalog.types import JSONPrimitive, JSONValue

__all__ = [
    "ActionDefinition",
    "CatalogFragment",
    "CatalogIntegrityError",
    "CatalogSnapshot",
    "CatalogValidationError",
    "CommandDefinition",
    "DiagnosticsBundle",
    "DiagnosticsDefinition",
    "DocumentationBundle",
    "DocumentationEntry",
    "JSONPrimitive",
    "JSONValue",
    "OptionDefinition",
    "OptionDocumentationBundle",
    "OptionGroupDefinition",
    "ParserDefinition",
    "RuntimeDefinition",
    "RuntimeInstallDefinition",
    "StrategyConfigField",
    "StrategyDefinition",
    "StrategyReference",
    "StrategyType",
    "SuppressionsDefinition",
    "ToolCatalogLoader",
    "ToolDefinition",
]
