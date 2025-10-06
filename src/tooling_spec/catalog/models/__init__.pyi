# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

from __future__ import annotations

from typing import Final

from ..model_actions import (
    ActionDefinition as ActionDefinition,
    ActionExecution as ActionExecution,
)
from ..model_catalog import (
    CatalogFragment as CatalogFragment,
    CatalogSnapshot as CatalogSnapshot,
)
from ..model_diagnostics import (
    DiagnosticsBundle as DiagnosticsBundle,
    DiagnosticsDefinition as DiagnosticsDefinition,
    SuppressionsDefinition as SuppressionsDefinition,
)
from ..model_documentation import (
    DocumentationBundle as DocumentationBundle,
    DocumentationEntry as DocumentationEntry,
)
from ..model_options import (
    OptionDefinition as OptionDefinition,
    OptionDocumentationBundle as OptionDocumentationBundle,
    OptionGroupDefinition as OptionGroupDefinition,
    OptionType as OptionType,
)
from ..model_references import (
    CommandDefinition as CommandDefinition,
    ParserDefinition as ParserDefinition,
    StrategyReference as StrategyReference,
)
from ..model_runtime import (
    RuntimeDefinition as RuntimeDefinition,
    RuntimeInstallDefinition as RuntimeInstallDefinition,
    RuntimeType as RuntimeType,
)
from ..model_strategy import (
    StrategyConfigField as StrategyConfigField,
    StrategyDefinition as StrategyDefinition,
    StrategyImplementation as StrategyImplementation,
    StrategyMetadata as StrategyMetadata,
    StrategyType as StrategyType,
)
from ..model_tool import (
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

CATALOG_MODEL_EXPORTS: Final[tuple[str, ...]] = (
    "ActionDefinition",
    "ActionExecution",
    "CatalogFragment",
    "CatalogSnapshot",
    "CommandDefinition",
    "DiagnosticsBundle",
    "DiagnosticsDefinition",
    "DocumentationBundle",
    "DocumentationEntry",
    "OptionDefinition",
    "OptionDocumentationBundle",
    "OptionGroupDefinition",
    "OptionType",
    "ParserDefinition",
    "RuntimeDefinition",
    "RuntimeInstallDefinition",
    "RuntimeType",
    "StrategyConfigField",
    "StrategyDefinition",
    "StrategyImplementation",
    "StrategyMetadata",
    "StrategyReference",
    "StrategyType",
    "SuppressionsDefinition",
    "ToolBehaviour",
    "ToolComponents",
    "ToolDefinition",
    "ToolFiles",
    "ToolIdentity",
    "ToolMetadata",
    "ToolOrdering",
    "parse_documentation_bundle",
    "parse_runtime_definition",
    "parse_tool_metadata",
    "TOOL_MODEL_EXPORTS",
    "TOOL_MODEL_OBJECTS",
)
