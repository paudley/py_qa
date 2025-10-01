# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Public export surface for catalog model primitives.

This package aggregates the most commonly consumed catalog constructs into a
single namespace so downstream tooling can depend on a concise, curated API.
"""

from __future__ import annotations

from typing import Final

from ..model_actions import ActionDefinition, ActionExecution
from ..model_catalog import CatalogFragment, CatalogSnapshot
from ..model_diagnostics import (
    DiagnosticsBundle,
    DiagnosticsDefinition,
    SuppressionsDefinition,
)
from ..model_documentation import DocumentationBundle, DocumentationEntry
from ..model_options import (
    OptionDefinition,
    OptionDocumentationBundle,
    OptionGroupDefinition,
    OptionType,
)
from ..model_references import CommandDefinition, ParserDefinition, StrategyReference
from ..model_runtime import RuntimeDefinition, RuntimeInstallDefinition, RuntimeType
from ..model_strategy import (
    StrategyConfigField,
    StrategyDefinition,
    StrategyImplementation,
    StrategyMetadata,
    StrategyType,
)
from ..model_tool import (
    TOOL_MODEL_EXPORTS,
    TOOL_MODEL_OBJECTS,
    ToolBehaviour,
    ToolDefinition,
    ToolFiles,
    ToolIdentity,
    ToolMetadata,
    ToolOrdering,
    parse_documentation_bundle,
    parse_runtime_definition,
    parse_tool_metadata,
)

_CATALOG_BASE_EXPORTS: Final[tuple[tuple[str, object], ...]] = (
    ("ActionDefinition", ActionDefinition),
    ("ActionExecution", ActionExecution),
    ("CatalogFragment", CatalogFragment),
    ("CatalogSnapshot", CatalogSnapshot),
    ("CommandDefinition", CommandDefinition),
    ("DiagnosticsBundle", DiagnosticsBundle),
    ("DiagnosticsDefinition", DiagnosticsDefinition),
    ("DocumentationBundle", DocumentationBundle),
    ("DocumentationEntry", DocumentationEntry),
    ("OptionDefinition", OptionDefinition),
    ("OptionDocumentationBundle", OptionDocumentationBundle),
    ("OptionGroupDefinition", OptionGroupDefinition),
    ("OptionType", OptionType),
    ("ParserDefinition", ParserDefinition),
    ("RuntimeDefinition", RuntimeDefinition),
    ("RuntimeInstallDefinition", RuntimeInstallDefinition),
    ("RuntimeType", RuntimeType),
    ("StrategyConfigField", StrategyConfigField),
    ("StrategyDefinition", StrategyDefinition),
    ("StrategyImplementation", StrategyImplementation),
    ("StrategyMetadata", StrategyMetadata),
    ("StrategyReference", StrategyReference),
    ("StrategyType", StrategyType),
    ("SuppressionsDefinition", SuppressionsDefinition),
)


def _register_exports(exports: tuple[tuple[str, object], ...]) -> None:
    """Populate the module namespace with the provided *exports*."""

    module_globals = globals()
    for export_name, export_value in exports:
        module_globals[export_name] = export_value


_register_exports(_CATALOG_BASE_EXPORTS)

_TOOL_MODEL_OBJECT_LOOKUP: Final[dict[str, object]] = {
    "ToolBehaviour": ToolBehaviour,
    "ToolDefinition": ToolDefinition,
    "ToolFiles": ToolFiles,
    "ToolIdentity": ToolIdentity,
    "ToolMetadata": ToolMetadata,
    "ToolOrdering": ToolOrdering,
    "parse_documentation_bundle": parse_documentation_bundle,
    "parse_runtime_definition": parse_runtime_definition,
    "parse_tool_metadata": parse_tool_metadata,
}


def _build_tool_model_exports() -> tuple[tuple[str, object], ...]:
    """Return pairs of tool export names and their bound objects.

    Raises:
        RuntimeError: When ``model_tool`` provides inconsistent metadata.

    """

    exports: list[tuple[str, object]] = []
    try:
        iterator = zip(TOOL_MODEL_EXPORTS, TOOL_MODEL_OBJECTS, strict=True)
    except TypeError as error:  # pragma: no cover - defensive assertion
        raise RuntimeError("model_tool.TOOL_MODEL_EXPORTS and TOOL_MODEL_OBJECTS must be iterable.") from error
    for name, obj in iterator:
        expected = _TOOL_MODEL_OBJECT_LOOKUP.get(name)
        if expected is None:
            raise RuntimeError(f"model_tool.TOOL_MODEL_EXPORTS contains an unknown symbol: {name!r}")
        if expected is not obj:
            raise RuntimeError(
                f"model_tool.TOOL_MODEL_OBJECTS entry for {name!r} does not match the " "imported symbol."
            )
        exports.append((name, obj))
    missing_symbols = set(_TOOL_MODEL_OBJECT_LOOKUP).difference(TOOL_MODEL_EXPORTS)
    if missing_symbols:
        formatted = ", ".join(sorted(missing_symbols))
        raise RuntimeError(f"model_tool.TOOL_MODEL_EXPORTS is missing expected entries: {formatted}")
    return tuple(exports)


_TOOL_MODEL_EXPORTS: Final[tuple[tuple[str, object], ...]] = _build_tool_model_exports()

_register_exports(_TOOL_MODEL_EXPORTS)

_CATALOG_BASE_NAMES: Final[tuple[str, ...]] = tuple(name for name, _ in _CATALOG_BASE_EXPORTS)

CATALOG_MODEL_EXPORTS: Final[tuple[str, ...]] = (
    *_CATALOG_BASE_NAMES,
    *TOOL_MODEL_EXPORTS,
    "TOOL_MODEL_EXPORTS",
    "TOOL_MODEL_OBJECTS",
)
# Tuple of symbols that define the public catalog model API.

__all__: Final[list[str]] = list(CATALOG_MODEL_EXPORTS)  # pyright: ignore[reportUnsupportedDunderAll]
