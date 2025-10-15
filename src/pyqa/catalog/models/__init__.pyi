# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Typing re-exports for catalog model stubs."""

from __future__ import annotations

from typing import Final

from tooling_spec.catalog.models import (
    ActionDefinition as ActionDefinition,
    ActionExecution as ActionExecution,
    CatalogFragment as CatalogFragment,
    CatalogSnapshot as CatalogSnapshot,
    CommandDefinition as CommandDefinition,
    DiagnosticsBundle as DiagnosticsBundle,
    DiagnosticsDefinition as DiagnosticsDefinition,
    DocumentationBundle as DocumentationBundle,
    DocumentationEntry as DocumentationEntry,
    OptionDefinition as OptionDefinition,
    OptionDocumentationBundle as OptionDocumentationBundle,
    OptionGroupDefinition as OptionGroupDefinition,
    OptionType as OptionType,
    ParserDefinition as ParserDefinition,
    RuntimeDefinition as RuntimeDefinition,
    RuntimeInstallDefinition as RuntimeInstallDefinition,
    RuntimeType as RuntimeType,
    StrategyConfigField as StrategyConfigField,
    StrategyDefinition as StrategyDefinition,
    StrategyImplementation as StrategyImplementation,
    StrategyMetadata as StrategyMetadata,
    StrategyReference as StrategyReference,
    StrategyType as StrategyType,
    SuppressionsDefinition as SuppressionsDefinition,
    TOOL_MODEL_EXPORTS as TOOL_MODEL_EXPORTS,
    TOOL_MODEL_OBJECTS as TOOL_MODEL_OBJECTS,
    ToolBehaviour as ToolBehaviour,
    ToolComponents as ToolComponents,
    ToolDefinition as ToolDefinition,
    ToolFiles as ToolFiles,
    ToolIdentity as ToolIdentity,
    ToolMetadata as ToolMetadata,
    ToolOrdering as ToolOrdering,
    parse_documentation_bundle as parse_documentation_bundle,
    parse_runtime_definition as parse_runtime_definition,
    parse_tool_metadata as parse_tool_metadata,
)

CATALOG_MODEL_EXPORTS: Final[tuple[str, ...]]

__all__: Final[tuple[str, ...]]
"""Type definitions for catalog models."""
