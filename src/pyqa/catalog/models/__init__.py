# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Public export surface for catalog model primitives."""

from __future__ import annotations

from typing import Final

from tooling_spec.catalog import model_actions as _model_actions
from tooling_spec.catalog import model_catalog as _model_catalog
from tooling_spec.catalog import model_diagnostics as _model_diagnostics
from tooling_spec.catalog import model_documentation as _model_documentation
from tooling_spec.catalog import model_options as _model_options
from tooling_spec.catalog import model_references as _model_references
from tooling_spec.catalog import model_runtime as _model_runtime
from tooling_spec.catalog import model_strategy as _model_strategy
from tooling_spec.catalog import model_tool as _model_tool

ActionDefinition = _model_actions.ActionDefinition
ActionExecution = _model_actions.ActionExecution
CatalogFragment = _model_catalog.CatalogFragment
CatalogSnapshot = _model_catalog.CatalogSnapshot
CommandDefinition = _model_references.CommandDefinition
DiagnosticsBundle = _model_diagnostics.DiagnosticsBundle
DiagnosticsDefinition = _model_diagnostics.DiagnosticsDefinition
DocumentationBundle = _model_documentation.DocumentationBundle
DocumentationEntry = _model_documentation.DocumentationEntry
OptionDefinition = _model_options.OptionDefinition
OptionDocumentationBundle = _model_options.OptionDocumentationBundle
OptionGroupDefinition = _model_options.OptionGroupDefinition
OptionType = _model_options.OptionType
ParserDefinition = _model_references.ParserDefinition
RuntimeDefinition = _model_runtime.RuntimeDefinition
RuntimeInstallDefinition = _model_runtime.RuntimeInstallDefinition
RuntimeType = _model_runtime.RuntimeType
StrategyConfigField = _model_strategy.StrategyConfigField
StrategyDefinition = _model_strategy.StrategyDefinition
StrategyImplementation = _model_strategy.StrategyImplementation
StrategyMetadata = _model_strategy.StrategyMetadata
StrategyReference = _model_references.StrategyReference
StrategyType = _model_strategy.StrategyType
SuppressionsDefinition = _model_diagnostics.SuppressionsDefinition
ToolBehaviour = _model_tool.ToolBehaviour
ToolComponents = _model_tool.ToolComponents
ToolDefinition = _model_tool.ToolDefinition
ToolFiles = _model_tool.ToolFiles
ToolIdentity = _model_tool.ToolIdentity
ToolMetadata = _model_tool.ToolMetadata
ToolOrdering = _model_tool.ToolOrdering
TOOL_MODEL_EXPORTS = _model_tool.TOOL_MODEL_EXPORTS
TOOL_MODEL_OBJECTS = _model_tool.TOOL_MODEL_OBJECTS
parse_documentation_bundle = _model_tool.parse_documentation_bundle
parse_runtime_definition = _model_tool.parse_runtime_definition
parse_tool_metadata = _model_tool.parse_tool_metadata

__all__ = (
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

CATALOG_MODEL_EXPORTS: Final[tuple[str, ...]] = __all__
