# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Public export surface for catalog model primitives.

This package aggregates the most commonly consumed catalog constructs into a
single namespace so downstream tooling can depend on a concise, curated API.
The previous implementation relied on dynamically registering symbols via
``globals()`` to populate ``__all__``. Static analysis tools struggled to
understand that dynamic pattern, so the module now publishes an explicit,
typed export list while retaining runtime validation to ensure the catalog
metadata remains coherent.
"""

from __future__ import annotations

from typing import Final

from .. import model_actions as _model_actions
from .. import model_catalog as _model_catalog
from .. import model_diagnostics as _model_diagnostics
from .. import model_documentation as _model_documentation
from .. import model_options as _model_options
from .. import model_references as _model_references
from .. import model_runtime as _model_runtime
from .. import model_strategy as _model_strategy
from .. import model_tool as _model_tool

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

_EXPECTED_TOOL_MODEL_OBJECTS: Final[dict[str, object]] = {
    "ToolBehaviour": ToolBehaviour,
    "ToolComponents": ToolComponents,
    "ToolDefinition": ToolDefinition,
    "ToolFiles": ToolFiles,
    "ToolIdentity": ToolIdentity,
    "ToolMetadata": ToolMetadata,
    "ToolOrdering": ToolOrdering,
    "parse_documentation_bundle": parse_documentation_bundle,
    "parse_runtime_definition": parse_runtime_definition,
    "parse_tool_metadata": parse_tool_metadata,
}


def _validate_tool_model_exports() -> None:
    """Ensure tool metadata exports remain consistent with ``model_tool``.

    Raises:
        RuntimeError: If ``TOOL_MODEL_EXPORTS`` or ``TOOL_MODEL_OBJECTS`` drift from
            the definitions imported above.

    """

    try:
        iterator = zip(TOOL_MODEL_EXPORTS, TOOL_MODEL_OBJECTS, strict=True)
    except TypeError as error:  # pragma: no cover - defensive assertion
        raise RuntimeError(
            "model_tool.TOOL_MODEL_EXPORTS and TOOL_MODEL_OBJECTS must be iterable.",
        ) from error
    seen_symbols: set[str] = set()
    for name, obj in iterator:
        seen_symbols.add(name)
        expected = _EXPECTED_TOOL_MODEL_OBJECTS.get(name)
        if expected is None:
            raise RuntimeError(f"model_tool.TOOL_MODEL_EXPORTS contains an unknown symbol: {name!r}")
        if expected is not obj:
            raise RuntimeError(
                f"model_tool.TOOL_MODEL_OBJECTS entry for {name!r} does not match the imported symbol.",
            )
    missing_symbols = set(_EXPECTED_TOOL_MODEL_OBJECTS).difference(seen_symbols)
    if missing_symbols:
        formatted = ", ".join(sorted(missing_symbols))
        raise RuntimeError(f"model_tool.TOOL_MODEL_EXPORTS is missing expected entries: {formatted}")


_validate_tool_model_exports()

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
